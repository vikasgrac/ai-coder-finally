#!/usr/bin/env bash
set -e

CONTAINER_NAME="finally"
IMAGE_NAME="finally"
VOLUME_NAME="finally-data"
PORT=8000
ENV_FILE="$(dirname "$0")/../.env"

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
  echo "Warning: .env file not found at $ENV_FILE"
  echo "Copy .env.example to .env and add your API keys."
fi

# Build image if needed or if --build flag passed
if [[ "$1" == "--build" ]] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  echo "Building Docker image..."
  docker build -t "$IMAGE_NAME" "$(dirname "$0")/.."
fi

# Stop existing container if running
if docker ps -q --filter "name=$CONTAINER_NAME" | grep -q .; then
  echo "Stopping existing container..."
  docker stop "$CONTAINER_NAME" &>/dev/null || true
  docker rm "$CONTAINER_NAME" &>/dev/null || true
fi

# Start the container
DOCKER_ARGS=(-d --name "$CONTAINER_NAME" -p "$PORT:8000" -v "$VOLUME_NAME:/app/db")
if [ -f "$ENV_FILE" ]; then
  DOCKER_ARGS+=(--env-file "$ENV_FILE")
fi
DOCKER_ARGS+=("$IMAGE_NAME")

docker run "${DOCKER_ARGS[@]}"

echo ""
echo "FinAlly is running at http://localhost:$PORT"

# Open browser (macOS)
if command -v open &>/dev/null; then
  sleep 2
  open "http://localhost:$PORT"
fi
