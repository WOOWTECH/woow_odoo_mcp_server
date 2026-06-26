# Odoo MCP Admin Bundle — Admin GUI + MCP Proxy + MCP Server in one container
#
# Build:
#   docker build -t woow-odoo-mcp-server .
#   podman build -t woow-odoo-mcp-server .
#
# Run:
#   docker run -p 8080:8080 -v ./data:/data woow-odoo-mcp-server
#   podman run -p 8080:8080 -v ./data:/data woow-odoo-mcp-server

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/
RUN cd frontend && npm install --production=false
COPY frontend/ frontend/
RUN cd frontend && npm run build

# Stage 2: Python runtime
FROM python:3.12-slim
WORKDIR /app

# Install Odoo MCP server + SSE transport support
RUN pip install --no-cache-dir odoo-mcp-server "mcp[cli]"

# Install the unified package (core + odoo admin)
COPY pyproject.toml /tmp/pkg/
COPY mcp_admin_core/ /tmp/pkg/mcp_admin_core/
COPY odoo_mcp_admin/ /tmp/pkg/odoo_mcp_admin/
RUN pip install --no-cache-dir /tmp/pkg/ && rm -rf /tmp/pkg/

# Copy frontend build
COPY --from=frontend-builder /build/frontend/dist /app/static

# Config volume
RUN mkdir -p /data
VOLUME /data

# Single port — admin GUI + MCP proxy
EXPOSE 8080

ENV MCP_ADMIN_CONFIG=/data/config.json

CMD ["uvicorn", "odoo_mcp_admin.main:app", "--host", "0.0.0.0", "--port", "8080"]
