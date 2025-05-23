async function pingBot() {
  const res = await fetch("/api/ping");
  const data = await res.json();
  document.getElementById("pingResult").textContent = JSON.stringify(data, null, 2);
}

async function getUser() {
  const userId = document.getElementById("userId").value;
  const res = await fetch(`/api/user/${userId}`);
  const data = await res.json();
  document.getElementById("userResult").textContent = JSON.stringify(data, null, 2);
}

async function loadGuilds() {
  const res = await fetch("/api/guilds");
  const data = await res.json();
  const list = document.getElementById("guildList");
  list.innerHTML = "";

  for (const guild of data.guilds) {
    const item = document.createElement("li");
    item.textContent = `${guild.name} (ID: ${guild.id}, Members: ${guild.member_count})`;
    list.appendChild(item);
  }
}
let userId = null;

async function loadGuilds() {
  if (!userId) {
    userId = prompt("Enter your Discord User ID (from login response):");
    if (!userId) {
      alert("User ID required.");
      return;
    }
  }

  const res = await fetch("/api/guilds", {
    headers: {
      "X-User-ID": userId
    }
  });

  const list = document.getElementById("guildList");
  list.innerHTML = "";

  if (!res.ok) {
    const error = await res.json();
    list.innerHTML = `<li>Error: ${error.error || "Unknown error"}</li>`;
    return;
  }

  const data = await res.json();

  for (const guild of data.guilds) {
    const item = document.createElement("li");
    item.textContent = `${guild.name} (ID: ${guild.id}, Members: ${guild.member_count})`;
    list.appendChild(item);
  }
}
