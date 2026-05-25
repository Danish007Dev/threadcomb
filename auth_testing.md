Auth-Gated App Testing Playbook
Step 1: Create Test User & Session
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"

Step 2: Test Backend API
# Test auth endpoint
curl -X GET "https://your-app.com/api/auth/me" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

Step 3: Browser Testing
// Set cookie and navigate
await page.context.add_cookies([{
    "name": "session_token",
    "value": "YOUR_SESSION_TOKEN",
    "domain": "your-app.com",
    "path": "/",
    "httpOnly": true,
    "secure": true,
    "sameSite": "None"
}]);
await page.goto("https://your-app.com");

Checklist:
- User document has user_id field (custom UUID)
- Session user_id matches user's user_id exactly
- All queries use {"_id": 0} projection to exclude MongoDB's _id
- Backend queries use user_id
- API returns user data (not 401/404)
- Browser loads dashboard (not login page)

For ThreadComb specifically:
- Test creator collection has creator_id (custom UUID), google_sub (Google subject ID), email
- creator_sessions collection has session_token, creator_id, expires_at
- Backend endpoints: /api/auth/me, /api/auth/session, /api/auth/logout
- Onboarding endpoints: /api/onboarding/{creator_id}/step-1, step-2, step-3, step-4
