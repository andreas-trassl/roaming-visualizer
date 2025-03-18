const svg = d3.select("#animation");

// Get dynamic width/height from the container
const width = document.querySelector(".left").clientWidth;
const height = document.querySelector(".left").clientHeight;

// Dynamically calculate image sizes based on screen height
const apSize = height * 0.5;
const clientSize = height * 0.25;

// Shift Left: Adjust X Position Based on Screen Width
const leftShift = width * 0.05;

// AP Positions (top-left of the AP images)
// Note: For the demo, we assume:
// "3. Obergeschoss" corresponds to AP1 and "Erdgeschoss" corresponds to AP2.
const ap1 = { name: "3. Obergeschoss", x: width * 0.35 - apSize / 2 - leftShift, y: 0 };
const ap2 = { name: "1. Obergeschoss", x: width * 0.35 - apSize / 2 - leftShift, y: height - apSize };

// Client Position (initially near AP1)
let client = { x: ap1.x + apSize + 20, y: ap1.y };

// Resize SVG dynamically
svg.attr("width", width).attr("height", height);

// Helper: Compute the center of an AP image
function getAPCenter(ap) {
  // AP image is drawn at (ap.x - apSize*0.4, ap.y - apSize*0.4) with width = apSize*1.8
  return {
    x: (ap.x - apSize * 0.4) + (apSize * 1.8) / 2,
    y: (ap.y - apSize * 0.4) + (apSize * 1.8) / 2
  };
}

// Draw AP1
svg.append("image")
    .attr("xlink:href", "assets/AP_with_logo.png")
    .attr("width", apSize * 1.8)
    .attr("height", apSize * 2)
    .attr("x", ap1.x - apSize * 0.25 )
    .attr("y", 0);

// Draw Client Device
const clientImg = svg.append("image")
    .attr("xlink:href", "assets/Client_with_logo.png")
    .attr("width", clientSize * 1.85)
    .attr("height", clientSize * 1.85)
    .attr("x", client.x - clientSize * 0.5)
    .attr("y", client.y);

// Helper: Get the center position of the client image
function getClientCenter() {
  return {
    x: parseFloat(clientImg.attr("x")) + clientSize,
    y: parseFloat(clientImg.attr("y")) + clientSize
  };
}

// Global variable to track the current AP display name (to avoid reanimation if unchanged)
let currentAPDisplay = "3. Obergeschoss";

// Function to move the client to a new AP using the target AP object
function moveClientToAP(targetAP) {
  const newAPCenter = getAPCenter(targetAP);

  // Animate the client movement vertically.
  clientImg.transition()
      .duration(2000)
      .attr("y", targetAP.y)
      .on("end", function() {
        // Additional animation end logic can be placed here if needed.
      });
}

// WebSocket connection and UI updates
const socket = new WebSocket("ws://localhost:8080");

socket.addEventListener("open", () => {
  console.log("WebSocket connection opened.");
});

socket.addEventListener("message", (event) => {
  try {
    const data = JSON.parse(event.data);
    if (data.servedBy !== undefined) {
      // Update UI metrics.
      document.getElementById("connectedAP").textContent = `${data.servedBy}`;
      document.getElementById("roamingCount").textContent = data.roamingCount;
      document.getElementById("uptime").textContent = data.uptime;
      document.getElementById("packetLosses").textContent = data.packet_losses_dl + data.packet_losses_ul;
      console.log("Received metrics from WebSocket:", data);
      
      // Map display names to target AP objects.
      let targetAP;
      if (data.servedBy === "3. Obergeschoss") {
          targetAP = ap1;
      } else if (data.servedBy === "1. Obergeschoss") {
          targetAP = ap2;
      } else {
          console.warn("Unknown AP display name received:", data.servedBy);
          return;
      }
      
      // Trigger movement only if the display name has changed.
      if (data.servedBy !== currentAPDisplay) {
        currentAPDisplay = data.servedBy;
        moveClientToAP(targetAP);
      } else {
        console.log("ServedBy value unchanged. No movement triggered.");
      }
    }
  } catch (e) {
    console.error("Error parsing WebSocket message:", e);
  }
});

socket.addEventListener("error", (event) => {
  console.error("WebSocket error:", event);
});

socket.addEventListener("close", (event) => {
  console.warn("WebSocket closed:", event);
});

// Reset button functionality: send a reset command to the Python backend.
const resetButton = document.getElementById("reset-button");
resetButton.addEventListener("click", () => {
  if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ command: "reset" }));
      console.log("Reset command sent to Python backend.");
  } else {
      console.warn("WebSocket is not open. Cannot send reset command.");
  }
});
