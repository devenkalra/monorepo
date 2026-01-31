#!/bin/bash

# Google OAuth Setup Script
# This script helps you set up Google OAuth for your Django application

set -e

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                                                                   ║"
echo "║           Google OAuth Setup for Django + React                  ║"
echo "║                                                                   ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: Please run this script from the data-backend directory"
    exit 1
fi

echo "📋 Step 1: Checking Django setup..."
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Virtual environment not activated. Activating..."
    source .venv/bin/activate
fi

echo "✓ Virtual environment: $VIRTUAL_ENV"
echo ""

echo "📋 Step 2: Running migrations..."
python manage.py migrate
echo ""

echo "📋 Step 3: Creating superuser (if needed)..."
echo ""
echo "Do you need to create a superuser? (y/n)"
read -r create_superuser

if [ "$create_superuser" = "y" ]; then
    python manage.py createsuperuser
fi

echo ""
echo "📋 Step 4: Google OAuth Credentials"
echo ""
echo "To set up Google OAuth, you need to:"
echo "1. Go to https://console.cloud.google.com/"
echo "2. Create a new project or select existing one"
echo "3. Enable Google+ API"
echo "4. Create OAuth 2.0 credentials"
echo ""
echo "Have you created Google OAuth credentials? (y/n)"
read -r has_credentials

if [ "$has_credentials" = "y" ]; then
    echo ""
    echo "Enter your Google OAuth Client ID:"
    read -r client_id
    
    echo "Enter your Google OAuth Client Secret:"
    read -r client_secret
    
    echo ""
    echo "📋 Step 5: Configuring Django..."
    
    # Start Django server in background
    python manage.py runserver 8001 > /dev/null 2>&1 &
    DJANGO_PID=$!
    
    echo "⏳ Waiting for Django server to start..."
    sleep 3
    
    echo ""
    echo "✓ Django server started (PID: $DJANGO_PID)"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  NEXT STEPS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. Open Django Admin: http://localhost:8001/admin/"
    echo ""
    echo "2. Log in with your superuser credentials"
    echo ""
    echo "3. Go to 'Sites' and update the domain to: localhost:8001"
    echo ""
    echo "4. Go to 'Social applications' → 'Add social application'"
    echo "   - Provider: Google"
    echo "   - Name: Google OAuth"
    echo "   - Client id: $client_id"
    echo "   - Secret key: $client_secret"
    echo "   - Sites: Select 'localhost:8001'"
    echo ""
    echo "5. In Google Cloud Console, add these redirect URIs:"
    echo "   - http://localhost:3000/auth/google/callback"
    echo "   - http://localhost:8001/accounts/google/login/callback/"
    echo ""
    echo "6. Start the frontend:"
    echo "   cd frontend"
    echo "   npm run dev"
    echo ""
    echo "7. Test the login at: http://localhost:3000/login"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Press Enter to stop the Django server and exit..."
    read -r
    
    kill $DJANGO_PID
    echo "✓ Django server stopped"
else
    echo ""
    echo "Please follow the instructions in GOOGLE_OAUTH_SETUP.md to:"
    echo "1. Create Google OAuth credentials"
    echo "2. Configure Django admin"
    echo "3. Test the OAuth flow"
    echo ""
    echo "Then run this script again."
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                                                                   ║"
echo "║  📖 For detailed instructions, see GOOGLE_OAUTH_SETUP.md         ║"
echo "║                                                                   ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
