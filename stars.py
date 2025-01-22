import requests
import csv

def get_starred_repositories(token):
    url = "https://api.github.com/user/starred"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    repositories = []
    page = 1

    while True:
        response = requests.get(url, headers=headers, params={"page": page, "per_page": 100})

        if response.status_code != 200:
            print(f"Error: {response.status_code}, {response.json()}\nExiting.")
            break

        data = response.json()

        if not data:
            break

        for repo in data:
            repo_data = {
                "name": repo.get("name"),
                "owner": repo.get("owner", {}).get("login"),
                "description": repo.get("description"),
                "url": repo.get("html_url"),
                "tags": ", ".join(repo.get("topics", [])),
            }
            repositories.append(repo_data)

        page += 1

    return repositories

def save_to_csv(repositories, filename):
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["name", "owner", "description", "url", "tags"])
        writer.writeheader()
        writer.writerows(repositories)

def main():
    token = input("Enter your GitHub personal access token: ")
    
    print("Fetching starred repositories...")
    repositories = get_starred_repositories(token)

    if repositories:
        filename = "starred_repositories.csv"
        save_to_csv(repositories, filename)
        print(f"Saved {len(repositories)} repositories to {filename}.")
    else:
        print("No repositories found or an error occurred.")

if __name__ == "__main__":
    main()
