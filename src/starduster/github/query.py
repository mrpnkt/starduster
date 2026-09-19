"""GraphQL documents.

Kept as data so the pagination logic in `client.py` stays generic and the
field selections are reviewable in one place.
"""

from __future__ import annotations

from ..config import README_PATHS

# `viewer` resolves to the owner of the token. Under GitHub Actions the default
# GITHUB_TOKEN belongs to github-actions[bot], which has no stars — a user PAT
# with read:user is required. See the workflow for the STARS_TOKEN secret.
STARS_QUERY = """
query Stars($pageSize: Int!, $cursor: String) {
  rateLimit { cost remaining }
  viewer {
    starredRepositories(
      first: $pageSize
      after: $cursor
      orderBy: {field: STARRED_AT, direction: DESC}
    ) {
      totalCount
      pageInfo { endCursor hasNextPage }
      edges {
        starredAt
        node {
          nameWithOwner
          description
          url
          stargazerCount
          pushedAt
          isArchived
          isFork
          primaryLanguage { name }
          licenseInfo { spdxId }
          repositoryTopics(first: 25) { nodes { topic { name } } }
        }
      }
    }
  }
}
"""


def _readme_fields(indent: str = "      ") -> str:
    """Aliased `object(expression:)` selections, one per candidate filename.

    Aliases are numbered so `normalize.pick_readme` can resolve them in
    preference order without knowing the filenames.
    """
    return "\n".join(
        f'{indent}readme_{i}: object(expression: "HEAD:{path}") '
        "{ ... on Blob { text } }"
        for i, path in enumerate(README_PATHS)
    )


def readme_query(count: int) -> str:
    """Build a query fetching READMEs for `count` repos by owner/name.

    READMEs are blobs and far heavier than metadata, so they are fetched in
    their own pass at a smaller page size rather than inline with the star
    listing.
    """
    blocks = "\n".join(
        f"""  r{i}: repository(owner: $owner{i}, name: $name{i}) {{
    nameWithOwner
{_readme_fields()}
  }}"""
        for i in range(count)
    )
    params = ", ".join(
        f"$owner{i}: String!, $name{i}: String!" for i in range(count)
    )
    return f"query Readmes({params}) {{\n  rateLimit {{ cost remaining }}\n{blocks}\n}}"
