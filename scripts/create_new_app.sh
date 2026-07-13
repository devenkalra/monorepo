#!/bin/bash
# Script to safely add a new Python app to the 'libs' folder in an Nx workspace.
# Usage: ./add-lib.sh my-new-lib-name

if [ -z "$1" ]; then
  echo "Error: Please provide a name for the new app."
  echo "Usage: $0 <app-name>"
  exit 1
fi

LIB_NAME=$1
APP_FOLDER="apps/$LIB_NAME"
SRC_FOLDER="$LIB_NAME"
PROJECT_ROOT=$(pwd)

echo "--- 1. Cleaning Nx Cache ---"
npx nx reset

if [ -d "$APP_FOLDER" ]; then
  echo "Error: Directory $APP_FOLDER already exists. Aborting."
  exit 1
fi

echo "--- 2. Creating Directory Structure: $APP_FOLDER ---"
mkdir -p "$APP_FOLDER/$SRC_FOLDER"
mkdir -p "$APP_FOLDER/tests"
touch "$APP_FOLDER/$SRC_FOLDER/__init__.py"
touch "$APP_FOLDER/tests/conftest.py"
touch "$APP_FOLDER/tests/test_$LIB_NAME.py"

echo "--- 3. Initializing Poetry project ---"
cd "$APP_FOLDER" || exit 1
# -n for non-interactive mode
poetry init --name "$LIB_NAME" -n

# Update pyproject.toml to use the compatible Python range (>=3.9, <4.0)
sed -i 's/python = ">=3.10"/python = ">=3.9,<4.0"/' pyproject.toml

echo "--- 4. Creating project.json configuration ---"
# Create the project.json file using the embedded template (replace placeholders)
cat <<EOF > project.json
{
  "name": "$LIB_NAME",
  "root": "$APP_FOLDER",
  "projectType": "app",
  "sourceRoot": "$APP_FOLDER/$SRC_FOLDER",
  "targets": {
    "build": {
      "executor": "@nxlv/python:poetry-build",
      "outputs": [
        "{workspaceRoot}/dist/$APP_FOLDER"
      ],
      "options": {}
    },
    "lint": {
      "executor": "@nxlv/python:flake8",
      "outputs": [
        "{workspaceRoot}/dist/pylint/$APP_FOLDER"
      ],
      "options": {
        "outputFile": "dist/pylint/$APP_FOLDER/report.txt"
      }
    },
    "test": {
      "executor": "@nxlv/python:pytest",
      "outputs": [
        "{workspaceRoot}/coverage/$APP_FOLDER"
      ],
      "options": {
        "codeCoverage": true,
        "junitOutput": true,
        "outputFile": "coverage/$APP_FOLDER/report.xml"
      }
    },
    "install": {
      "executor": "@nx/exec:exec",
      "options": {
        "command": "poetry install"
      }
    },
    "add": {
      "executor": "@nxlv/python:poetry-add"
    },
    "update-lock": {
      "executor": "@nxlv/python:poetry-update"
    }
  },
  "tags": ["python", "lib", "${LIB_NAME//-/,}"]
}
EOF

cd "$PROJECT_ROOT" || exit 1

echo "--- 5. Registering in nx.json ---"
# Use 'jq' (JSON processor) to safely insert the new project into nx.json
if command -v jq &> /dev/null; then
    jq ".projects += {\"$LIB_NAME\": \"$APP_FOLDER\"}" nx.json > nx.json.tmp && mv nx.json.tmp nx.json
    echo "nx.json updated successfully with jq."
else
    echo "Warning: 'jq' not found. Please manually add the following to nx.json:"
    echo "\"$LIB_NAME\": \"$APP_FOLDER\""
fi

echo "--- 6. Running Poetry Install (via direct command) ---"
# Use the working direct command to set up the environment
cd "$APP_FOLDER" || exit 1
poetry install

echo "--- ✅ SUCCESS! $LIB_NAME has been created and configured. ---"
echo "You can now run: npx nx test $LIB_NAME"