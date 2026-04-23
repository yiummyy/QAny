# /docker

Manage Docker containers for this project.

## Steps
1. Check container status: `docker compose ps`
2. If containers are not running: `docker compose up -d`
3. Check container health: `docker compose logs --tail=20`
4. Report any unhealthy containers or errors
5. Verify services are accessible on their configured ports

## Constraints
- Never run `docker system prune` or remove volumes without explicit confirmation
- Do not modify Dockerfile or docker-compose files without explaining the changes first
- Always use `-d` flag for `up` to avoid blocking the terminal
