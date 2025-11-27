import json
import os

def generate_auth_file():
    """Generate client authentication file from environment variables"""
    
    client_username = os.environ.get('CLIENT_USERNAME')
    client_password = os.environ.get('CLIENT_PASSWORD')
    
    if not client_username or not client_password:
        print("⚠️  CLIENT_USERNAME and CLIENT_PASSWORD not set, using defaults")
        client_username = "client"
        client_password = "change_me_please"
    
    auth_data = {
        "username": client_username,
        "password": client_password
    }
    
    # Save to data directory
    os.makedirs('data', exist_ok=True)
    with open('data/client_auth.json', 'w') as f:
        json.dump(auth_data, f)
    
    print(f"✅ Client authentication file created")

if __name__ == "__main__":
    generate_auth_file()
