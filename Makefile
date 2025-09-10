# Polly Docker Management Makefile

.PHONY: help build up down logs status update update-all restart clean deploy deploy-all deploy-no-cleanup clean-images

# Default target
help:
	@echo "🚀 Polly Docker Management Commands"
	@echo "=================================="
	@echo ""
	@echo "Development & Deployment:"
	@echo "  make deploy       - Git pull + update Polly + cleanup images (recommended)"
	@echo "  make deploy-all   - Git pull + rebuild all containers + cleanup"
	@echo "  make deploy-no-cleanup - Git pull + update Polly (no cleanup, faster)"
	@echo "  make update       - Update only Polly container (keeps Redis unchanged)"
	@echo "  make update-all   - Update both Polly and Redis containers"
	@echo "  make restart      - Restart containers without rebuilding"
	@echo ""
	@echo "Basic Operations:"
	@echo "  make build        - Build all containers"
	@echo "  make up           - Start all containers"
	@echo "  make down         - Stop all containers"
	@echo ""
	@echo "Monitoring:"
	@echo "  make logs         - Show all container logs"
	@echo "  make logs-polly   - Show only Polly logs"
	@echo "  make logs-redis   - Show only Redis logs"
	@echo "  make status       - Show container status"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean        - Remove containers and unused images"
	@echo "  make clean-images - Clean old Docker images and build cache"
	@echo "  make clean-all    - Remove everything including volumes"

# Update only Polly container (most common use case)
update:
	@echo "📦 Updating Polly container only..."
	docker-compose down polly
	docker-compose build --no-cache polly
	docker-compose up -d
	@echo "✅ Polly container updated!"

# Update all containers
update-all:
	@echo "📦 Updating all containers..."
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d
	@echo "✅ All containers updated!"

# Restart without rebuilding
restart:
	@echo "🔄 Restarting containers..."
	docker-compose restart
	@echo "✅ Containers restarted!"

# Build containers
build:
	docker-compose build

# Start containers
up:
	docker-compose up -d

# Stop containers
down:
	docker-compose down

# Show all logs
logs:
	docker-compose logs -f

# Show only Polly logs
logs-polly:
	docker-compose logs -f polly

# Show only Redis logs
logs-redis:
	docker-compose logs -f redis

# Show container status
status:
	@echo "📊 Container Status:"
	@echo "=================="
	@docker-compose ps
	@echo ""
	@echo "🔄 Recent Activity:"
	@echo "=================="
	@docker-compose logs --tail=10 polly
	@echo ""
	@echo "💾 Redis Info:"
	@echo "=============="
	@docker-compose exec redis redis-cli --no-auth-warning -a "${REDIS_PASSWORD:-polly_redis_pass}" info replication 2>/dev/null || echo "Redis not accessible"

# Clean up containers and unused images
clean:
	@echo "🧹 Cleaning up containers and unused images..."
	docker-compose down
	docker system prune -f
	@echo "✅ Cleanup completed!"

# Clean everything including volumes (WARNING: This will delete Redis data!)
clean-all:
	@echo "⚠️  WARNING: This will delete ALL data including Redis cache!"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || exit 1
	docker-compose down -v
	docker system prune -af
	@echo "✅ Complete cleanup finished!"

# Complete deployment with git pull (most common use case)
deploy:
	@echo "🚀 Deploying latest code with cleanup..."
	./scripts/deploy-clean.sh

# Complete deployment rebuilding everything
deploy-all:
	@echo "🚀 Full deployment with all containers..."
	./scripts/deploy-clean.sh --all

# Deploy without cleanup (faster but uses more disk)
deploy-no-cleanup:
	@echo "🚀 Deploying without cleanup (faster)..."
	./scripts/deploy.sh

# Clean Docker images and build cache
clean-images:
	@echo "🧹 Cleaning Docker images and build cache..."
	@echo "Before cleanup:"
	@docker system df 2>/dev/null || echo "Could not check Docker disk usage"
	@echo ""
	# Remove dangling images
	@docker images -f 'dangling=true' -q | xargs -r docker rmi 2>/dev/null || true
	# Clean build cache older than 24h
	@docker builder prune -f --filter="until=24h" 2>/dev/null || true
	@echo "After cleanup:"
	@docker system df 2>/dev/null || echo "Could not check Docker disk usage"
	@echo "✅ Image cleanup completed!"

# Quick health check
health:
	@echo "🩺 Health Check:"
	@echo "==============="
	@echo "Polly health endpoint:"
	@curl -f -s http://localhost:8000/health && echo " ✅ Healthy" || echo " ❌ Unhealthy"
	@echo "Redis ping:"
	@docker-compose exec -T redis redis-cli --no-auth-warning -a "${REDIS_PASSWORD:-polly_redis_pass}" ping 2>/dev/null && echo " ✅ Healthy" || echo " ❌ Unhealthy"
