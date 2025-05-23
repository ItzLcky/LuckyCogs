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
