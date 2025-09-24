"""
Poll management commands for Polly CLI
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from cli.utils.cli_helpers import CLIHelpers, DatabaseHelper, format_datetime, truncate_text


class PollCommands:
    """Poll management command handlers"""
    
    def __init__(self):
        self.helpers = CLIHelpers()
        self.logger = logging.getLogger(__name__)
    
    async def handle_command(self, args) -> int:
        """Route poll commands to appropriate handlers"""
        try:
            if args.command == 'show':
                return await self.show_poll(args.poll_id, args.include_votes)
            elif args.command == 'list':
                return await self.list_polls(
                    status=args.status,
                    guild_id=args.guild,
                    author_id=args.author,
                    limit=args.limit,
                    sort_by=args.sort
                )
            elif args.command == 'force-update':
                return await self.force_update_poll(args.poll_id, args.dry_run)
            elif args.command == 'search':
                return await self.search_polls(args.query, args.fields)
            elif args.command == 'close':
                return await self.close_poll(args.poll_id, args.reason, args.force)
            elif args.command == 'reopen':
                return await self.reopen_poll(args.poll_id, args.duration)
            elif args.command == 'validate':
                return await self.validate_polls(args.fix, args.poll_id)
            else:
                self.helpers.error(f"Unknown poll command: {args.command}")
                return 1
        except Exception as e:
            self.helpers.error(f"Command failed: {str(e)}")
            self.logger.exception("Poll command error")
            return 1
    
    async def show_poll(self, poll_id: int, include_votes: bool = False) -> int:
        """Show detailed information about a specific poll"""
        try:
            async for session in DatabaseHelper.get_db_session():
                # Import here to avoid circular imports
                from polly.database import Poll, PollOption, Vote
                from sqlalchemy.orm import joinedload
                from sqlalchemy import func
                
                # Get poll with options
                poll = await session.get(
                    Poll, 
                    poll_id,
                    options=[joinedload(Poll.options)]
                )
                
                if not poll:
                    self.helpers.error(f"Poll {poll_id} not found")
                    return 1
                
                # Get vote statistics
                vote_counts = await session.execute(
                    session.query(PollOption.id, PollOption.text, func.count(Vote.id).label('votes'))
                    .outerjoin(Vote)
                    .filter(PollOption.poll_id == poll_id)
                    .group_by(PollOption.id, PollOption.text)
                )
                
                vote_stats = {option_id: {'text': text, 'votes': votes} 
                             for option_id, text, votes in vote_counts}
                
                # Prepare poll data
                poll_data = {
                    "ID": poll.id,
                    "Title": poll.title,
                    "Description": poll.description or "No description",
                    "Status": poll.status,
                    "Author ID": poll.author_id,
                    "Guild ID": poll.guild_id,
                    "Channel ID": poll.channel_id,
                    "Message ID": poll.discord_poll_message_id,
                    "Created": format_datetime(poll.created_at),
                    "Updated": format_datetime(poll.updated_at),
                    "Opens": format_datetime(poll.opens_at),
                    "Closes": format_datetime(poll.closes_at),
                    "Allow Multiple": "Yes" if poll.allow_multiple_votes else "No",
                    "Show Results": poll.show_results_to if poll.show_results_to else "Everyone",
                    "Total Votes": sum(stats['votes'] for stats in vote_stats.values())
                }
                
                self.helpers.output(poll_data)
                
                # Show options with vote counts
                if poll.options:
                    self.helpers._print_title("Poll Options")
                    options_data = []
                    for option in poll.options:
                        stats = vote_stats.get(option.id, {'votes': 0})
                        options_data.append([
                            option.id,
                            truncate_text(option.text, 60),
                            stats['votes'],
                            f"{(stats['votes'] / max(poll_data['Total Votes'], 1)) * 100:.1f}%"
                        ])
                    
                    self.helpers.table(
                        ["Option ID", "Text", "Votes", "Percentage"],
                        options_data
                    )
                
                # Show detailed votes if requested
                if include_votes and poll_data['Total Votes'] > 0:
                    votes = await session.execute(
                        session.query(Vote.user_id, Vote.option_id, Vote.created_at)
                        .join(PollOption)
                        .filter(PollOption.poll_id == poll_id)
                        .order_by(Vote.created_at.desc())
                    )
                    
                    self.helpers._print_title("Individual Votes")
                    vote_data = []
                    for user_id, option_id, created_at in votes:
                        option_text = next(
                            (opt.text for opt in poll.options if opt.id == option_id),
                            f"Option {option_id}"
                        )
                        vote_data.append([
                            user_id,
                            truncate_text(option_text, 40),
                            format_datetime(created_at)
                        ])
                    
                    self.helpers.table(
                        ["User ID", "Option", "Voted At"],
                        vote_data
                    )
                
                return 0
        except Exception as e:
            self.helpers.error(f"Failed to show poll: {str(e)}")
            return 1
    
    async def list_polls(self, status: Optional[str] = None, guild_id: Optional[int] = None, 
                        author_id: Optional[int] = None, limit: int = 20, 
                        sort_by: str = 'created') -> int:
        """List polls with optional filters"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll
                from sqlalchemy import desc, asc
                
                query = session.query(Poll)
                
                # Apply filters
                if status:
                    query = query.filter(Poll.status == status)
                if guild_id:
                    query = query.filter(Poll.guild_id == guild_id)
                if author_id:
                    query = query.filter(Poll.author_id == author_id)
                
                # Apply sorting
                if sort_by == 'created':
                    query = query.order_by(desc(Poll.created_at))
                elif sort_by == 'updated':
                    query = query.order_by(desc(Poll.updated_at))
                elif sort_by == 'closes_at':
                    query = query.order_by(asc(Poll.closes_at))
                
                # Apply limit
                query = query.limit(limit)
                
                polls = await session.execute(query)
                polls_list = polls.scalars().all()
                
                if not polls_list:
                    self.helpers.info("No polls found matching criteria")
                    return 0
                
                # Prepare table data
                headers = ["ID", "Title", "Status", "Guild", "Author", "Created", "Closes"]
                rows = []
                
                for poll in polls_list:
                    rows.append([
                        poll.id,
                        truncate_text(poll.title, 30),
                        poll.status,
                        poll.guild_id,
                        poll.author_id,
                        format_datetime(poll.created_at),
                        format_datetime(poll.closes_at)
                    ])
                
                filter_info = []
                if status:
                    filter_info.append(f"status={status}")
                if guild_id:
                    filter_info.append(f"guild={guild_id}")
                if author_id:
                    filter_info.append(f"author={author_id}")
                
                title = f"Polls (limit={limit}"
                if filter_info:
                    title += f", {', '.join(filter_info)}"
                title += ")"
                
                self.helpers.table(headers, rows, title)
                return 0
        except Exception as e:
            self.helpers.error(f"Failed to list polls: {str(e)}")
            return 1
    
    async def force_update_poll(self, poll_id: int, dry_run: bool = False) -> int:
        """Force update Discord message from database state"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll
                from polly.services.discord.discord_utils import update_poll_message
                from polly.discord_bot import get_bot_instance
                
                poll = await session.get(Poll, poll_id)
                if not poll:
                    self.helpers.error(f"Poll {poll_id} not found")
                    return 1
                
                if dry_run:
                    self.helpers.info(f"Would update Discord message for poll {poll_id}")
                    self.helpers.output({
                        "poll_id": poll.id,
                        "title": poll.title,
                        "status": poll.status,
                        "message_id": poll.discord_poll_message_id,
                        "channel_id": poll.channel_id,
                        "guild_id": poll.guild_id
                    })
                    return 0
                
                # Get bot instance
                bot = get_bot_instance()
                if not bot:
                    self.helpers.error("Discord bot not available")
                    return 1
                
                # Update message
                success = await update_poll_message(bot, poll.id)
                
                if success:
                    self.helpers.success(f"Successfully updated Discord message for poll {poll_id}")
                    return 0
                else:
                    self.helpers.error(f"Failed to update Discord message for poll {poll_id}")
                    return 1
        except Exception as e:
            self.helpers.error(f"Failed to force update poll: {str(e)}")
            return 1
    
    async def search_polls(self, query: str, fields: List[str]) -> int:
        """Search polls by text content"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll, PollOption
                from sqlalchemy import or_
                
                base_query = session.query(Poll)
                conditions = []
                
                # Build search conditions
                if 'title' in fields:
                    conditions.append(Poll.title.ilike(f'%{query}%'))
                if 'description' in fields:
                    conditions.append(Poll.description.ilike(f'%{query}%'))
                if 'options' in fields:
                    # Search in poll options
                    option_subquery = session.query(PollOption.poll_id).filter(
                        PollOption.text.ilike(f'%{query}%')
                    )
                    conditions.append(Poll.id.in_(option_subquery))
                
                if not conditions:
                    self.helpers.error("No valid search fields specified")
                    return 1
                
                # Execute search
                search_query = base_query.filter(or_(*conditions)).order_by(Poll.updated_at.desc())
                results = await session.execute(search_query)
                polls = results.scalars().all()
                
                if not polls:
                    self.helpers.info(f"No polls found matching '{query}'")
                    return 0
                
                # Display results
                self.helpers._print_title(f"Search Results for '{query}' (found {len(polls)})")
                
                for poll in polls:
                    poll_data = {
                        "ID": poll.id,
                        "Title": poll.title,
                        "Status": poll.status,
                        "Created": format_datetime(poll.created_at),
                        "Description": truncate_text(poll.description or "", 100)
                    }
                    self.helpers.output(poll_data)
                    print()  # Add spacing between results
                
                return 0
        except Exception as e:
            self.helpers.error(f"Failed to search polls: {str(e)}")
            return 1
    
    async def close_poll(self, poll_id: int, reason: Optional[str] = None, force: bool = False) -> int:
        """Manually close a poll"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.services.poll.poll_closure_service import PollClosureService
                
                # Check if poll exists and can be closed
                from polly.database import Poll
                poll = await session.get(Poll, poll_id)
                if not poll:
                    self.helpers.error(f"Poll {poll_id} not found")
                    return 1
                
                if poll.status == 'closed' and not force:
                    self.helpers.error(f"Poll {poll_id} is already closed. Use --force to force close.")
                    return 1
                
                if not force and not self.helpers.confirm(f"Close poll {poll_id} '{poll.title}'?"):
                    self.helpers.info("Operation cancelled")
                    return 0
                
                # Close the poll
                closure_service = PollClosureService()
                result = await closure_service.close_poll(poll_id, reason or "Manually closed via CLI")
                
                if result["success"]:
                    self.helpers.success(f"Successfully closed poll {poll_id}")
                    if result.get("stats"):
                        self.helpers.output(result["stats"])
                    return 0
                else:
                    self.helpers.error(f"Failed to close poll: {result.get('error', 'Unknown error')}")
                    return 1
        except Exception as e:
            self.helpers.error(f"Failed to close poll: {str(e)}")
            return 1
    
    async def reopen_poll(self, poll_id: int, duration: Optional[int] = None) -> int:
        """Reopen a closed poll"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll
                
                poll = await session.get(Poll, poll_id)
                if not poll:
                    self.helpers.error(f"Poll {poll_id} not found")
                    return 1
                
                if poll.status != 'closed':
                    self.helpers.error(f"Poll {poll_id} is not closed (current status: {poll.status})")
                    return 1
                
                if not self.helpers.confirm(f"Reopen poll {poll_id} '{poll.title}'?"):
                    self.helpers.info("Operation cancelled")
                    return 0
                
                # Set new close time if duration provided
                new_closes_at = poll.closes_at
                if duration:
                    new_closes_at = datetime.utcnow() + timedelta(minutes=duration)
                
                # Update poll status
                poll.status = 'active'
                poll.closes_at = new_closes_at
                poll.updated_at = datetime.utcnow()
                
                await session.commit()
                
                # Update Discord message
                try:
                    from polly.services.discord.discord_utils import update_poll_message
                    from polly.discord_bot import get_bot_instance
                    
                    bot = get_bot_instance()
                    if bot:
                        await update_poll_message(bot, poll_id)
                except Exception as e:
                    self.helpers.warning(f"Poll reopened but Discord update failed: {str(e)}")
                
                self.helpers.success(f"Successfully reopened poll {poll_id}")
                self.helpers.info(f"New close time: {format_datetime(new_closes_at)}")
                return 0
        except Exception as e:
            self.helpers.error(f"Failed to reopen poll: {str(e)}")
            return 1
    
    async def validate_polls(self, fix_issues: bool = False, poll_id: Optional[int] = None) -> int:
        """Validate poll data integrity"""
        try:
            async for session in DatabaseHelper.get_db_session():
                from polly.database import Poll, PollOption
                from sqlalchemy import func
                
                # Build query
                query = session.query(Poll)
                if poll_id:
                    query = query.filter(Poll.id == poll_id)
                
                polls = await session.execute(query)
                poll_list = polls.scalars().all()
                
                if not poll_list:
                    self.helpers.info("No polls found to validate")
                    return 0
                
                issues_found = 0
                issues_fixed = 0
                
                self.helpers._print_title(f"Validating {len(poll_list)} polls...")
                
                for poll in poll_list:
                    poll_issues = []
                    
                    # Check for missing required fields
                    if not poll.title:
                        poll_issues.append("Missing title")
                    if not poll.guild_id:
                        poll_issues.append("Missing guild_id")
                    if not poll.channel_id:
                        poll_issues.append("Missing channel_id")
                    
                    # Check date consistency
                    if poll.opens_at and poll.closes_at and poll.opens_at >= poll.closes_at:
                        poll_issues.append("opens_at >= closes_at")
                    
                    # Check status consistency
                    now = datetime.utcnow()
                    expected_status = 'scheduled'
                    if poll.opens_at and now >= poll.opens_at:
                        expected_status = 'active'
                    if poll.closes_at and now >= poll.closes_at:
                        expected_status = 'closed'
                    
                    if poll.status != expected_status:
                        poll_issues.append(f"Status mismatch: {poll.status} vs expected {expected_status}")
                        
                        if fix_issues:
                            poll.status = expected_status
                            poll.updated_at = now
                            issues_fixed += 1
                    
                    # Check for orphaned options
                    options_count = await session.execute(
                        session.query(func.count(PollOption.id)).filter(PollOption.poll_id == poll.id)
                    )
                    option_count = options_count.scalar()
                    
                    if option_count == 0:
                        poll_issues.append("No poll options found")
                    
                    if poll_issues:
                        issues_found += len(poll_issues)
                        self.helpers.warning(f"Poll {poll.id}: {', '.join(poll_issues)}")
                
                if fix_issues and issues_fixed > 0:
                    await session.commit()
                    self.helpers.success(f"Fixed {issues_fixed} issues")
                
                if issues_found == 0:
                    self.helpers.success("No issues found - all polls are valid")
                else:
                    self.helpers.info(f"Found {issues_found} issues across {len(poll_list)} polls")
                    if not fix_issues:
                        self.helpers.info("Use --fix to attempt automatic repairs")
                
                return 0 if issues_found == 0 else 1
        except Exception as e:
            self.helpers.error(f"Failed to validate polls: {str(e)}")
            return 1