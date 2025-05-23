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
