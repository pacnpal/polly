"""
Admin management commands for Polly CLI
"""

import logging
import json
import csv
import os
import sys
from typing import List, Optional
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from cli.utils.cli_helpers import CLIHelpers, DatabaseHelper, format_datetime, truncate_text


class AdminCommands:
    """Admin management command handlers"""
    
    def __init__(self):
        self.helpers = CLIHelpers()
        self.logger = logging.getLogger(__name__)
    
    async def handle_command(self, args) -> int:
        """Route admin commands to appropriate handlers"""
        try:
            if args.command == 'user':
                return await self.user_operations(args)
            elif args.command == 'bulk':
                return await self.bulk_operations(args)
            elif args.command == 'export':
                return await self.export_data(args.output_file, args.format, args.poll_ids)
            elif args.command == 'import':
                return await self.import_data(args.input_file, args.dry_run)
            else:
                self.helpers.error(f"Unknown admin command: {args.command}")
                return 1
        except Exception as e:
            self.helpers.error(f"Admin command failed: {str(e)}")
            self.logger.exception("Admin command error")
            return 1
    
    async def user_operations(self, args) -> int:
        """Handle user management operations"""
        try:
            if not hasattr(args, 'user_action') or not args.user_action:
                self.helpers.error("No user action specified")
                return 1
            
            if args.user_action == 'show':
                return await self.show_user(args.user_id)
            elif args.user_action == 'list':
                return await self.list_users(args.role, args.guild)
            else:
                self.helpers.error(f"Unknown user action: {args.user_action}")
                return 1
                
        except Exception as e:
            self.helpers.error(f"User operation failed: {str(e)}")
            return 1
    
    async def show_user(self, user_id: int) -> int:
        """Show detailed user information"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll, Vote
                from sqlalchemy import func
                
                # Get user's polls
                user_polls = await session.execute(
                    session.query(Poll)
                    .filter(Poll.author_id == user_id)
                    .order_by(Poll.created_at.desc())
                )
                polls = user_polls.scalars().all()
                
                # Get user's votes
                user_votes = await session.execute(
                    session.query(func.count(Vote.id))
                    .filter(Vote.user_id == user_id)
                )
                vote_count = user_votes.scalar()
                
                # Get poll statistics
                poll_stats = {
                    'total': len(polls),
                    'active': len([p for p in polls if p.status == 'active']),
                    'scheduled': len([p for p in polls if p.status == 'scheduled']),
                    'closed': len([p for p in polls if p.status == 'closed'])
                }
                
                user_data = {
                    "User ID": user_id,
                    "Total Polls Created": poll_stats['total'],
                    "Active Polls": poll_stats['active'],
                    "Scheduled Polls": poll_stats['scheduled'],
                    "Closed Polls": poll_stats['closed'],
                    "Total Votes Cast": vote_count,
                    "First Poll": format_datetime(polls[-1].created_at) if polls else "Never",
                    "Latest Poll": format_datetime(polls[0].created_at) if polls else "Never"
                }
                
                self.helpers.output(user_data)
                
                # Show recent polls
                if polls:
                    recent_polls = polls[:10]  # Last 10 polls
                    self.helpers._print_title("Recent Polls")
                    
                    poll_rows = []
                    for poll in recent_polls:
                        poll_rows.append([
                            poll.id,
                            truncate_text(poll.title, 40),
                            poll.status,
                            format_datetime(poll.created_at),
                            poll.guild_id
                        ])
                    
                    self.helpers.table(
                        ["Poll ID", "Title", "Status", "Created", "Guild"],
                        poll_rows
                    )
                
                return 0
        except Exception as e:
            self.helpers.error(f"Failed to show user: {str(e)}")
            return 1
    
    async def list_users(self, role: Optional[str] = None, guild_id: Optional[int] = None) -> int:
        """List users with optional filters"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll
                from sqlalchemy import func, distinct
                
                # Get users with poll activity
                query = session.query(
                    Poll.author_id,
                    func.count(Poll.id).label('poll_count'),
                    func.max(Poll.created_at).label('last_activity'),
                    func.count(distinct(Poll.guild_id)).label('guild_count')
                ).group_by(Poll.author_id)
                
                if guild_id:
                    query = query.filter(Poll.guild_id == guild_id)
                
                query = query.order_by(func.max(Poll.created_at).desc())
                
                results = await session.execute(query)
                users = results.fetchall()
                
                if not users:
                    self.helpers.info("No users found")
                    return 0
                
                # Prepare table data
                headers = ["User ID", "Polls Created", "Last Activity", "Guilds", "Status"]
                rows = []
                
                for user_id, poll_count, last_activity, guild_count in users:
                    # Determine user status based on recent activity
                    days_since_activity = (datetime.utcnow() - last_activity).days if last_activity else 999
                    if days_since_activity <= 7:
                        status = "Active"
                    elif days_since_activity <= 30:
                        status = "Recent"
                    else:
                        status = "Inactive"
                    
                    rows.append([
                        user_id,
                        poll_count,
                        format_datetime(last_activity),
                        guild_count,
                        status
                    ])
                
                filter_info = []
                if guild_id:
                    filter_info.append(f"guild={guild_id}")
                if role:
                    filter_info.append(f"role={role}")
                
                title = f"Users ({len(users)} found"
                if filter_info:
                    title += f", {', '.join(filter_info)}"
                title += ")"
                
                self.helpers.table(headers, rows, title)
                return 0
                
        except Exception as e:
            self.helpers.error(f"Failed to list users: {str(e)}")
            return 1
    
    async def bulk_operations(self, args) -> int:
        """Handle bulk operations"""
        try:
            if not hasattr(args, 'bulk_action') or not args.bulk_action:
                self.helpers.error("No bulk action specified")
                return 1
            
            if args.bulk_action == 'close':
                return await self.bulk_close_polls(
                    status=args.status,
                    guild_id=args.guild,
                    older_than_days=args.older_than,
                    dry_run=args.dry_run
                )
            else:
                self.helpers.error(f"Unknown bulk action: {args.bulk_action}")
                return 1
                
        except Exception as e:
            self.helpers.error(f"Bulk operation failed: {str(e)}")
            return 1
    
    async def bulk_close_polls(self, status: Optional[str] = None, guild_id: Optional[int] = None,
                              older_than_days: Optional[int] = None, dry_run: bool = False) -> int:
        """Bulk close polls matching criteria"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll
                
                query = session.query(Poll)
                
                # Apply filters
                if status:
                    query = query.filter(Poll.status == status)
                else:
                    # Default to active and scheduled polls
                    query = query.filter(Poll.status.in_(['active', 'scheduled']))
                
                if guild_id:
                    query = query.filter(Poll.guild_id == guild_id)
                
                if older_than_days:
                    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
                    query = query.filter(Poll.created_at < cutoff_date)
                
                # Get matching polls
                results = await session.execute(query)
                polls_to_close = results.scalars().all()
                
                if not polls_to_close:
                    self.helpers.info("No polls found matching criteria")
                    return 0
                
                # Show what would be closed
                self.helpers._print_title(f"Polls to close ({len(polls_to_close)})")
                
                poll_rows = []
                for poll in polls_to_close:
                    poll_rows.append([
                        poll.id,
                        truncate_text(poll.title, 30),
                        poll.status,
                        format_datetime(poll.created_at),
                        poll.guild_id
                    ])
                
                self.helpers.table(
                    ["Poll ID", "Title", "Status", "Created", "Guild"],
                    poll_rows
                )
                
                if dry_run:
                    self.helpers.info("Dry run complete - no polls were closed")
                    return 0
                
                # Confirm operation
                if not self.helpers.confirm(f"Close {len(polls_to_close)} polls?"):
                    self.helpers.info("Operation cancelled")
                    return 0
                
                # Close polls
                closed_count = 0
                failed_count = 0
                
                for poll in polls_to_close:
                    try:
                        poll.status = 'closed'
                        poll.updated_at = datetime.utcnow()
                        closed_count += 1
                        
                        # Update progress
                        self.helpers.progress_bar(
                            closed_count + failed_count,
                            len(polls_to_close),
                            "Closing polls: "
                        )
                        
                    except Exception as e:
                        self.logger.error(f"Failed to close poll {poll.id}: {str(e)}")
                        failed_count += 1
                
                await session.commit()
                
                self.helpers.success(f"Successfully closed {closed_count} polls")
                if failed_count > 0:
                    self.helpers.warning(f"Failed to close {failed_count} polls")
                
                return 0 if failed_count == 0 else 1
                
        except Exception as e:
            self.helpers.error(f"Bulk close operation failed: {str(e)}")
            return 1
    
    async def export_data(self, output_file: str, format_type: str = 'json', 
                         poll_ids: Optional[List[int]] = None) -> int:
        """Export poll data to file"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll, PollOption, Vote
                from sqlalchemy.orm import joinedload
                
                # Build query
                query = session.query(Poll).options(joinedload(Poll.options))
                
                if poll_ids:
                    query = query.filter(Poll.id.in_(poll_ids))
                
                polls = await session.execute(query)
                poll_list = polls.scalars().all()
                
                if not poll_list:
                    self.helpers.info("No polls found to export")
                    return 0
                
                self.helpers.info(f"Exporting {len(poll_list)} polls to {output_file}")
                
                if format_type == 'json':
                    export_data = []
                    for poll in poll_list:
                        # Get votes for this poll
                        votes = await session.execute(
                            session.query(Vote)
                            .join(PollOption)
                            .filter(PollOption.poll_id == poll.id)
                        )
                        vote_list = votes.scalars().all()
                        
                        poll_data = {
                            "id": poll.id,
                            "title": poll.title,
                            "description": poll.description,
                            "status": poll.status,
                            "author_id": poll.author_id,
                            "guild_id": poll.guild_id,
                            "channel_id": poll.channel_id,
                            "created_at": poll.created_at.isoformat() if poll.created_at else None,
                            "updated_at": poll.updated_at.isoformat() if poll.updated_at else None,
                            "opens_at": poll.opens_at.isoformat() if poll.opens_at else None,
                            "closes_at": poll.closes_at.isoformat() if poll.closes_at else None,
                            "allow_multiple_votes": poll.allow_multiple_votes,
                            "show_results_to": poll.show_results_to,
                            "options": [
                                {
                                    "id": option.id,
                                    "text": option.text,
                                    "emoji": option.emoji
                                }
                                for option in poll.options
                            ],
                            "votes": [
                                {
                                    "user_id": vote.user_id,
                                    "option_id": vote.option_id,
                                    "created_at": vote.created_at.isoformat() if vote.created_at else None
                                }
                                for vote in vote_list
                            ]
                        }
                        export_data.append(poll_data)
                    
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(export_data, f, indent=2, ensure_ascii=False)
                
                elif format_type == 'csv':
                    with open(output_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        
                        # Write header
                        writer.writerow([
                            'poll_id', 'title', 'description', 'status', 'author_id',
                            'guild_id', 'channel_id', 'created_at', 'updated_at',
                            'opens_at', 'closes_at', 'allow_multiple_votes',
                            'show_results_to', 'option_count', 'vote_count'
                        ])
                        
                        # Write poll data
                        for poll in poll_list:
                            votes = await session.execute(
                                session.query(Vote)
                                .join(PollOption)
                                .filter(PollOption.poll_id == poll.id)
                            )
                            vote_count = len(votes.scalars().all())
                            
                            writer.writerow([
                                poll.id,
                                poll.title,
                                poll.description or '',
                                poll.status,
                                poll.author_id,
                                poll.guild_id,
                                poll.channel_id,
                                poll.created_at.isoformat() if poll.created_at else '',
                                poll.updated_at.isoformat() if poll.updated_at else '',
                                poll.opens_at.isoformat() if poll.opens_at else '',
                                poll.closes_at.isoformat() if poll.closes_at else '',
                                poll.allow_multiple_votes,
                                poll.show_results_to or '',
                                len(poll.options),
                                vote_count
                            ])
                
                self.helpers.success(f"Successfully exported {len(poll_list)} polls to {output_file}")
                return 0
                
        except Exception as e:
            self.helpers.error(f"Export failed: {str(e)}")
            return 1
    
    async def import_data(self, input_file: str, dry_run: bool = False) -> int:
        """Import poll data from file"""
        try:
            if not os.path.exists(input_file):
                self.helpers.error(f"Input file not found: {input_file}")
                return 1
            
            # Determine file format
            if input_file.endswith('.json'):
                with open(input_file, 'r', encoding='utf-8') as f:
                    import_data = json.load(f)
            else:
                self.helpers.error("Only JSON import is currently supported")
                return 1
            
            if not isinstance(import_data, list):
                self.helpers.error("Import data must be a list of polls")
                return 1
            
            self.helpers.info(f"Importing {len(import_data)} polls from {input_file}")
            
            if dry_run:
                # Validate data structure
                valid_count = 0
                invalid_count = 0
                
                for i, poll_data in enumerate(import_data):
                    try:
                        # Basic validation
                        required_fields = ['title', 'author_id', 'guild_id', 'channel_id', 'options']
                        missing_fields = [field for field in required_fields if field not in poll_data]
                        
                        if missing_fields:
                            self.helpers.warning(f"Poll {i+1}: Missing fields: {', '.join(missing_fields)}")
                            invalid_count += 1
                        else:
                            valid_count += 1
                            
                    except Exception as e:
                        self.helpers.error(f"Poll {i+1}: Validation error: {str(e)}")
                        invalid_count += 1
                
                self.helpers.info(f"Validation complete: {valid_count} valid, {invalid_count} invalid")
                return 0 if invalid_count == 0 else 1
            
            else:
                # Actually import the data
                async for session in DatabaseHelper.get_db_session():
                    from polly.database import Poll, PollOption
                    
                    imported_count = 0
                    failed_count = 0
                    
                    for i, poll_data in enumerate(import_data):
                        try:
                            # Create poll
                            poll = Poll(
                                title=poll_data['title'],
                                description=poll_data.get('description'),
                                status=poll_data.get('status', 'scheduled'),
                                author_id=poll_data['author_id'],
                                guild_id=poll_data['guild_id'],
                                channel_id=poll_data['channel_id'],
                                allow_multiple_votes=poll_data.get('allow_multiple_votes', False),
                                show_results_to=poll_data.get('show_results_to'),
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            
                            session.add(poll)
                            await session.flush()  # Get poll ID
                            
                            # Create options
                            for option_data in poll_data.get('options', []):
                                option = PollOption(
                                    poll_id=poll.id,
                                    text=option_data['text'],
                                    emoji=option_data.get('emoji')
                                )
                                session.add(option)
                            
                            imported_count += 1
                            
                            # Update progress
                            self.helpers.progress_bar(
                                imported_count + failed_count,
                                len(import_data),
                                "Importing polls: "
                            )
                            
                        except Exception as e:
                            self.logger.error(f"Failed to import poll {i+1}: {str(e)}")
                            failed_count += 1
                    
                    await session.commit()
                    
                    self.helpers.success(f"Successfully imported {imported_count} polls")
                    if failed_count > 0:
                        self.helpers.warning(f"Failed to import {failed_count} polls")
                    
                    return 0 if failed_count == 0 else 1
                
        except Exception as e:
            self.helpers.error(f"Import failed: {str(e)}")
            return 1