function loadCSV() {
  const csvFilePath = "starred_repositories.csv";
  fetch(csvFilePath)
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.text();
    })
    .then(csvText => {
      const parsedData = Papa.parse(csvText, {
        header: true,
        skipEmptyLines: true,
      });
      repositories = parsedData.data;
      renderTableAndTags();
      addSortingToHeaders(); // Add sorting
    })
    .catch(error => console.error("Error loading CSV:", error));
}

function renderTableAndTags() {
  const tableBody = document.querySelector("#repo-table tbody");
  const tagCloud = document.getElementById("tag-cloud");

  tableBody.innerHTML = "";
  const allTags = new Set();

  repositories.forEach(repo => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${repo.name}</td>
      <td>${repo.owner}</td>
      <td>${repo.description}</td>
      <td><a href="${repo.url}" target="_blank">${repo.url}</a></td>
      <td>${repo.tags}</td>
    `;
    tableBody.appendChild(row);

    if (repo.tags) {
      repo.tags.split(",").forEach(tag => allTags.add(tag.trim()));
    }
  });

  tagCloud.innerHTML = "";
  const sortedTags = Array.from(allTags).sort((a, b) => a.localeCompare(b));
  sortedTags.forEach(tag => {
    const tagElement = document.createElement("span");
    tagElement.className = "tag";
    tagElement.textContent = tag;
    tagElement.onclick = () => filterByTag(tag);
    tagCloud.appendChild(tagElement);
  });
}

function filterTable() {
  const query = document.getElementById("search-bar").value.toLowerCase();
  const rows = document.querySelectorAll("#repo-table tbody tr");

  rows.forEach(row => {
    const cells = row.querySelectorAll("td");
    const text = Array.from(cells).map(cell => cell.textContent.toLowerCase()).join(" ");
    row.style.display = text.includes(query) ? "" : "none";
  });
}

function filterByTag(tag) {
  const rows = document.querySelectorAll("#repo-table tbody tr");

  rows.forEach(row => {
    const tagsCell = row.querySelector("td:last-child").textContent;
    row.style.display = tagsCell.includes(tag) ? "" : "none";
  });
}

function resetFilters() {
  // Clear the search bar
  document.getElementById("search-bar").value = "";

  const rows = document.querySelectorAll("#repo-table tbody tr");
  rows.forEach(row => {
    row.style.display = "";
  });
}

function addSortingToHeaders() {
  const headers = document.querySelectorAll("#repo-table thead th");

  headers.forEach((header, index) => {
    header.style.cursor = "pointer"; 
    header.addEventListener("click", () => {
      sortTable(index);
    });
  });
}

function sortTable(columnIndex) {
  const table = document.getElementById("repo-table");
  const tbody = table.querySelector("tbody");
  const rows = Array.from(tbody.querySelectorAll("tr"));

  const isAscending = table.getAttribute("data-sort-order") === "asc";
  const newSortOrder = isAscending ? "desc" : "asc";
  table.setAttribute("data-sort-order", newSortOrder);

  rows.sort((rowA, rowB) => {
    const cellA = rowA.querySelectorAll("td")[columnIndex].textContent.trim();
    const cellB = rowB.querySelectorAll("td")[columnIndex].textContent.trim();

    if (columnIndex === 3) { // Special handling for URLs (column index 3)
      return isAscending ? cellA.localeCompare(cellB) : cellB.localeCompare(cellA);
    } else {
      return isAscending ? cellA.localeCompare(cellB, undefined, { numeric: true }) : cellB.localeCompare(cellA, undefined, { numeric: true });
    }
  });

  tbody.innerHTML = "";
  rows.forEach(row => tbody.appendChild(row));
}

document.addEventListener("DOMContentLoaded", () => {
  loadCSV(); 
});

function toggleTagCloud() {
  const tagCloudContainer = document.getElementById("tag-cloud-container");
  const toggleButton = document.getElementById("accordion-toggle");

  if (tagCloudContainer.style.display === "none") {
    tagCloudContainer.style.display = "inline-block";
    toggleButton.textContent = "Hide Tags";
  } else {
    tagCloudContainer.style.display = "none";
    toggleButton.textContent = "Show Tags";
  }
}
