import os
import urllib.request
import urllib.error
from google.oauth2 import id_token
from google.auth.transport.requests import Request
import google.auth

# Replace with your actual Cloud Run URL
CLOUD_RUN_URL = "https://threadcomb-backend-463179340371.asia-south1.run.app"

# We are going to test the invoice check endpoint
TEST_ENDPOINT = f"{CLOUD_RUN_URL}/internal/check-overdue-invoices"

def generate_valid_oidc_token(audience: str) -> str:
    """Generates a valid Google OIDC token signed by your service account."""
    credentials, project = google.auth.default()
    request = Request()
    # Ensure credentials are valid and refreshed
    credentials.refresh(request)
    
    # We use Google's metadata server or service account to fetch an ID token
    from google.auth.transport.requests import AuthorizedSession
    import google.oauth2.id_token
    
    try:
        token = google.oauth2.id_token.fetch_id_token(request, audience)
        return token
    except Exception as e:
        print(f"Failed to generate valid token. Ensure GOOGLE_APPLICATION_CREDENTIALS is set: {e}")
        return ""

def make_request(token: str, description: str):
    print(f"\n--- Testing: {description} ---")
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
        
    req = urllib.request.Request(TEST_ENDPOINT, headers=headers, method='POST')
    
    try:
        response = urllib.request.urlopen(req)
        print(f"✅ Result: SUCCESS (HTTP {response.getcode()})")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"🛡️ Result: BLOCKED (HTTP 403 Forbidden)")
        else:
            print(f"❌ Result: UNEXPECTED ERROR (HTTP {e.code})")
        return False

if __name__ == "__main__":
    print(f"Testing OIDC Security for {TEST_ENDPOINT}")
    
    # Test 1: No Token
    make_request(None, "No Token Provided")
    
    # Test 2: Spoofed Token
    make_request("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake_payload.fake_signature", "Spoofed/Fake Token")
    
    # Test 3: Valid Token but Wrong Audience
    wrong_aud_token = generate_valid_oidc_token("https://wrong-audience.example.com")
    if wrong_aud_token:
        make_request(wrong_aud_token, "Valid Token signed by Google, but WRONG Audience")
    
    # Test 4: Fully Valid Token
    valid_token = generate_valid_oidc_token(CLOUD_RUN_URL)
    if valid_token:
        make_request(valid_token, "Fully Valid Token with CORRECT Audience")
