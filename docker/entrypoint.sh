#!/bin/sh
set -e

python -c "import migration_platform" 2>/dev/null || python -m migration_platform