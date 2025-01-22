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
  allTags.forEach(tag => {
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

document.addEventListener("DOMContentLoaded", () => {
  loadCSV(); // Load and parse the CSV file
});

function toggleTagCloud() {
  const tagCloudContainer = document.getElementById("tag-cloud-container");
  const toggleButton = document.getElementById("accordion-toggle");

  if (tagCloudContainer.style.display === "none") {
    tagCloudContainer.style.display = "block";
    toggleButton.textContent = "Hide Tags";
  } else {
    tagCloudContainer.style.display = "none";
    toggleButton.textContent = "Show Tags";
  }
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
  allTags.forEach(tag => {
    const tagElement = document.createElement("span");
    tagElement.className = "tag";
    tagElement.textContent = tag;
    tagElement.onclick = () => filterByTag(tag);
    tagCloud.appendChild(tagElement);
  });
}
