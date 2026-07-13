#!/bin/bash
#
# Install Frontend Testing Dependencies
#

echo "Installing frontend testing dependencies..."

npm install -D \
  vitest@^1.0.0 \
  @testing-library/react@^14.0.0 \
  @testing-library/jest-dom@^6.1.5 \
  @testing-library/user-event@^14.5.1 \
  jsdom@^23.0.0 \
  @vitest/ui@^1.0.0

echo ""
echo "✓ Testing dependencies installed successfully!"
echo ""
echo "You can now run tests with:"
echo "  npm test              # Run all tests"
echo "  npm run test:watch    # Watch mode"
echo "  npm run test:ui       # Open UI"
echo "  npm run test:coverage # With coverage"
