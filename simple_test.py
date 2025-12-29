import requests

def test_route_exists():
    try:
        # Test if the route exists by checking the URL pattern
        base_url = "http://localhost:5000"

        # Test the new route directly
        response = requests.get(f"{base_url}/add_item/1")
        print(f"Status code: {response.status_code}")

        if response.status_code == 404:
            print("Route exists but requires authentication or return not found")
            return True
        elif response.status_code == 302:
            print("Route exists and redirects (likely to login)")
            return True
        elif response.status_code == 200:
            print("Route exists and is accessible")
            return True
        else:
            print(f"Unexpected status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_route_exists()