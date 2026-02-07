/**
 * Authentication Setup for Integration Tests
 * 
 * This file handles login and creates authenticated state for tests.
 */
import { test as setup } from '@playwright/test';

const authFile = 'tests/integration/.auth/user.json';

setup('authenticate', async ({ page, request }) => {
  // Login via API
  const response = await request.post('http://localhost:8000/api/auth/login/', {
    data: {
      email: 'test@example.com',
      password: 'testpass123'
    }
  });

  if (!response.ok()) {
    // Try to register if login fails
    const registerResponse = await request.post('http://localhost:8000/api/auth/register/', {
      data: {
        email: 'test@example.com',
        password: 'testpass123',
        username: 'testuser'
      }
    });
    
    if (registerResponse.ok()) {
      // Login after registration
      await request.post('http://localhost:8000/api/auth/login/', {
        data: {
          email: 'test@example.com',
          password: 'testpass123'
        }
      });
    }
  }

  const data = await response.json();
  
  // Set authentication in localStorage
  await page.goto('http://localhost:5173');
  await page.evaluate((token) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('refresh_token', token);
  }, data.access);

  // Save authenticated state
  await page.context().storageState({ path: authFile });
});
