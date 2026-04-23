const express = require("express");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;

// Serve all static files from root
app.use(express.static(path.join(__dirname, "..", "..")));

// Explicit folders (optional but safer)
app.use("/css", express.static(path.join(__dirname, "..", "..", "css")));
app.use("/js", express.static(path.join(__dirname, "..", "..", "js")));
app.use("/data", express.static(path.join(__dirname, "..", "..", "data")));

// Routes
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "..", "..", "index.html"));
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
