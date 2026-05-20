#!/bin/bash

# Script to configure branch protection for the main branch
# This script uses the GitHub CLI (gh) to apply branch protection rules

set -e  # Exit on error

# Dynamically detect the current repository and branch
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
if [ -z "$REPO" ]; then
    echo -e "${RED}Error: Could not detect repository. Make sure you're in a git repo with a GitHub remote.${NC}"
    exit 1
fi
BRANCH="main"
CONFIG_FILE="$(dirname "$0")/branch-protection-config.json"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Branch Protection Setup"
echo "=========================================="
echo ""
echo "Repository: $REPO"
echo "Branch: $BRANCH"
echo "Config file: $CONFIG_FILE"
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: GitHub CLI (gh) is not installed.${NC}"
    echo ""
    echo "Please install it from: https://cli.github.com/"
    echo ""
    echo "On macOS: brew install gh"
    echo "On Linux: See https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo -e "${RED}Error: Not authenticated with GitHub CLI.${NC}"
    echo ""
    echo "Please run: gh auth login"
    exit 1
fi

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: Config file not found: $CONFIG_FILE${NC}"
    exit 1
fi

# Validate JSON
if ! python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
    echo -e "${RED}Error: Invalid JSON in config file${NC}"
    exit 1
fi

echo -e "${YELLOW}This will configure the following branch protection rules:${NC}"
echo ""
echo "✓ Require status checks to pass:"
echo "  - Resolve Runner Target"
echo "  - Lint and Code Quality"
echo "  - Coverage Check"
echo "  - Test Python 3.10"
echo "  - Test Python 3.11"
echo "  - Test Python 3.12"
echo "  - Security Checks"
echo "  - Validate Configuration"
echo "  - CI Status Check"
echo "✓ Require branches to be up to date before merging"
echo "✓ Require linear history (no merge commits)"
echo "✓ Require conversation resolution before merging"
echo "✓ Prevent force pushes to $BRANCH"
echo "✓ Prevent deletion of $BRANCH"
echo "✓ Apply rules to administrators"
echo ""
echo -e "${YELLOW}Note:${NC} PR approval is disabled for solo development (GitHub doesn't allow"
echo "self-approval). Protection still ensures CI passes and conversations are resolved."
echo ""

# Prompt for confirmation
read -p "Do you want to apply these settings? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Aborted.${NC}"
    exit 0
fi

echo ""
echo "Applying branch protection rules..."

# Apply the configuration
if gh api -X PUT "/repos/$REPO/branches/$BRANCH/protection" \
    --input "$CONFIG_FILE" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Branch protection successfully configured!${NC}"
    echo ""
    echo "You can view the settings at:"
    echo "https://github.com/$REPO/settings/branches"
else
    echo -e "${RED}✗ Failed to configure branch protection.${NC}"
    echo ""
    echo "Please check:"
    echo "1. You have admin access to the repository"
    echo "2. The repository exists: $REPO"
    echo "3. The branch exists: $BRANCH"
    echo "4. The status check names match your CI workflow"
    echo ""
    echo "You can also configure manually via the GitHub UI:"
    echo "https://github.com/$REPO/settings/branches"
    exit 1
fi

echo ""
echo "Next steps:"
echo "1. Create a test PR to verify the protection rules work"
echo "2. Ensure CI passes before attempting to merge"
echo "3. Review the full documentation in docs/BRANCH_PROTECTION.md"
echo ""
echo -e "${GREEN}Done!${NC}"
