#!/usr/bin/env bash

CONTAINER_NAME="finally"

if docker ps -q --filter "name=$CONTAINER_NAME" | grep -q .; then
  echo "Stopping FinAlly container..."
  docker stop "$CONTAINER_NAME"
  docker rm "$CONTAINER_NAME"
  echo "Done. Data volume preserved."
else
  echo "No running FinAlly container found."
fi
