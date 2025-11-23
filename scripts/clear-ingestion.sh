#!/bin/bash

# HomeSight AI Sidecar - Clear All Ingested Documents
# This script removes all cached PDFs and clears the ChromaDB RAG database

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  HomeSight AI Sidecar - Clear Ingestion                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Confirm before deleting
echo -e "${YELLOW}⚠️  This will delete:${NC}"
echo "  1. All cached PDF manuals (~/.homesight/manuals)"
echo "  2. ChromaDB RAG database (~/.homesight/rag)"
echo "  3. Ingestion audit log (.logs/ingestion.jsonl)"
echo ""
read -p "Are you sure? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
  echo -e "${YELLOW}Cancelled.${NC}"
  exit 0
fi

echo ""

# Stop AI Sidecar if running
echo -e "${BLUE}Stopping AI Sidecar...${NC}"
if docker ps | grep -q homesight-ai-sidecar; then
  docker stop homesight-ai-sidecar
  echo -e "${GREEN}✅ AI Sidecar stopped${NC}"
else
  echo -e "${YELLOW}ℹ️  AI Sidecar not running${NC}"
fi

echo ""

# Clear cached PDFs
echo -e "${BLUE}Clearing cached PDF manuals...${NC}"
if [ -d ~/.homesight/manuals ]; then
  rm -rf ~/.homesight/manuals
  mkdir -p ~/.homesight/manuals
  echo -e "${GREEN}✅ Cleared ~/.homesight/manuals${NC}"
else
  echo -e "${YELLOW}ℹ️  No manuals directory found${NC}"
fi

echo ""

# Clear RAG database
echo -e "${BLUE}Clearing RAG database...${NC}"
if [ -d ~/.homesight/rag ]; then
  rm -rf ~/.homesight/rag
  mkdir -p ~/.homesight/rag
  echo -e "${GREEN}✅ Cleared ~/.homesight/rag${NC}"
else
  echo -e "${YELLOW}ℹ️  No RAG directory found${NC}"
fi

echo ""

# Clear ingestion log
echo -e "${BLUE}Clearing ingestion audit log...${NC}"
if [ -f .logs/ingestion.jsonl ]; then
  rm -f .logs/ingestion.jsonl
  echo -e "${GREEN}✅ Cleared .logs/ingestion.jsonl${NC}"
else
  echo -e "${YELLOW}ℹ️  No ingestion log found${NC}"
fi

echo ""

# Restart AI Sidecar
echo -e "${BLUE}Restarting AI Sidecar...${NC}"
docker-compose up -d homesight-ai-sidecar
echo -e "${GREEN}✅ AI Sidecar restarted${NC}"

echo ""
echo -e "${GREEN}✨ Ingestion cleared successfully!${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo "  ✓ Cached PDFs cleared"
echo "  ✓ RAG database cleared (empty ChromaDB)"
echo "  ✓ Ingestion audit log cleared"
echo "  ✓ AI Sidecar restarted and ready"
echo ""
echo -e "${YELLOW}Next: Trigger device onboarding to re-ingest${NC}"
