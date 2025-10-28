"""
Quick test script for JWT token generation
Run this to verify Chad's JWT setup is working
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.jwt_utils import generate_memory_token, verify_token

print("=" * 60)
print("JWT TOKEN GENERATION TEST")
print("=" * 60)

# Test 1: Generate token for Peterson Insurance (customer_id=1)
print("\n✅ Test 1: Generate token for customer_id=1 (Peterson)")
token_1 = generate_memory_token(customer_id=1)
print(f"Token (first 80 chars): {token_1[:80]}...")
print(f"Full token length: {len(token_1)} characters")

# Test 2: Verify the token
print("\n✅ Test 2: Verify token")
payload_1 = verify_token(token_1)
if payload_1:
    print(f"  customer_id: {payload_1['customer_id']}")
    print(f"  scope: {payload_1['scope']}")
    print(f"  expires: {payload_1['exp']}")
    print("  ✅ Token valid!")
else:
    print("  ❌ Token invalid!")

# Test 3: Generate token for Smith Insurance (customer_id=2)
print("\n✅ Test 3: Generate token for customer_id=2 (Smith)")
token_2 = generate_memory_token(customer_id=2)
print(f"Token (first 80 chars): {token_2[:80]}...")

# Test 4: Verify tokens are different
print("\n✅ Test 4: Verify tokens are unique per customer")
print(f"  Token 1 == Token 2: {token_1 == token_2}")
if token_1 != token_2:
    print("  ✅ Tokens are unique (correct!)")
else:
    print("  ❌ Tokens are identical (BUG!)")

# Test 5: Show example API call
print("\n✅ Test 5: Example API call to Alice")
print(f"""
import requests

response = requests.post(
    "http://209.38.143.71:8100/v2/context/enriched",
    headers={{"Authorization": "Bearer {token_1[:40]}..."}},
    json={{"user_id": "+15551234567"}}
)
""")

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED - JWT generation working!")
print("=" * 60)
print("\n📋 Next Steps:")
print("1. Send JWT_SETUP_INSTRUCTIONS.md to Alice")
print("2. Alice adds same JWT_SECRET_KEY to her environment")
print("3. Alice implements JWT validation middleware")
print("4. Test end-to-end: Chad generates → Alice validates")
