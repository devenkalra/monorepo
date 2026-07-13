#!/bin/bash
# Script to safely add a new Python library to the 'libs' folder in an Nx workspace.
# Usage: ./add-lib.sh my-new-lib-name

if [ -z "$1" ]; then
  echo "Error: Please provide a name for the new library."
  echo "Usage: $0 <lib-name>"
  exit 1
fi

LIB_NAME=$1
LIB_FOLDER="libs/$LIB_NAME"
SRC_FOLDER="$LIB_NAME"
PROJECT_ROOT=$(pwd)

echo "--- 1. Cleaning Nx Cache ---"
npx nx reset

if [ -d "$LIB_FOLDER" ]; then
  echo "Error: Directory $LIB_FOLDER already exists. Aborting."
  exit 1
fi

echo "--- 2. Creating Directory Structure: $LIB_FOLDER ---"
mkdir -p "$LIB_FOLDER/$SRC_FOLDER"
mkdir -p "$LIB_FOLDER/tests"
touch "$LIB_FOLDER/$SRC_FOLDER/__init__.py"
touch "$LIB_FOLDER/tests/conftest.py"
touch "$LIB_FOLDER/tests/test_$LIB_NAME.py"

echo "--- 3. Initializing Poetry project ---"
cd "$LIB_FOLDER" || exit 1
# -n for non-interactive mode
poetry init --name "$LIB_NAME" -n

# Update pyproject.toml to use the compatible Python range (>=3.9, <4.0)
sed -i 's/python = ">=3.10"/python = ">=3.9,<4.0"/' pyproject.toml

echo "--- 4. Creating project.json configuration ---"
# Create the project.json file using the embedded template (replace placeholders)
cat <<EOF > project.json
{
  "name": "$LIB_NAME",
  "root": "$LIB_FOLDER",
  "projectType": "library",
  "sourceRoot": "$LIB_FOLDER/$SRC_FOLDER",
  "targets": {
    "build": {
      "executor": "@nxlv/python:poetry-build",
      "outputs": [
        "{workspaceRoot}/dist/$LIB_FOLDER"
      ],
      "options": {}
    },
    "lint": {
      "executor": "@nxlv/python:flake8",
      "outputs": [
        "{workspaceRoot}/dist/pylint/$LIB_FOLDER"
      ],
      "options": {
        "outputFile": "dist/pylint/$LIB_FOLDER/report.txt"
      }
    },
    "test": {
      "executor": "@nxlv/python:pytest",
      "outputs": [
        "{workspaceRoot}/coverage/$LIB_FOLDER"
      ],
      "options": {
        "codeCoverage": true,
        "junitOutput": true,
        "outputFile": "coverage/$LIB_FOLDER/report.xml"
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
    jq ".projects += {\"$LIB_NAME\": \"$LIB_FOLDER\"}" nx.json > nx.json.tmp && mv nx.json.tmp nx.json
    echo "nx.json updated successfully with jq."
else
    echo "Warning: 'jq' not found. Please manually add the following to nx.json:"
    echo "\"$LIB_NAME\": \"$LIB_FOLDER\""
fi

echo "--- 6. Running Poetry Install (via direct command) ---"
# Use the working direct command to set up the environment
cd "$LIB_FOLDER" || exit 1
poetry install

echo "--- ✅ SUCCESS! $LIB_NAME has been created and configured. ---"
echo "You can now run: npx nx test $LIB_NAME"