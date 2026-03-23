// backend/server.js
const express = require("express");
const mongoose = require("mongoose");
const bodyParser = require("body-parser");
const cors = require("cors");

// === CONFIG ===
const app = express();
app.use(bodyParser.json());
app.use(cors());

// MongoDB connection (palitan mo ng sarili mong MongoDB Atlas URI)
mongoose.connect("mongodb+srv://votingAdmin:secretPass@coevotingsystem.mhjm7sw.mongodb.net/coe_voting_system?retryWrites=true&w=majority")
  .then(() => console.log("MongoDB connected"))
  .catch(err => console.error("MongoDB connection error:", err));

// === TIME RESTRICTION MIDDLEWARE ===
// Voting allowed only March 22 00:00 to March 28 23:59 (Philippine Time)
function votingWindow(req, res, next) {
  const now = new Date();
  // Convert to Philippine Time (UTC+8)
  const phTime = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Manila" }));

  const start = new Date("2026-03-22T00:00:00+08:00");
  const end = new Date("2026-03-28T23:59:59+08:00");

  if (phTime < start || phTime > end) {
    return res.status(403).json({ message: "Voting Closed" });
  }
  next();
}

// === MODELS ===
const Ticket = mongoose.model("Ticket", new mongoose.Schema({
  ticket_id: String,
  used_dates: [
    {
      date: String,   // YYYY-MM-DD
      gender: String, // "male" or "female"
    }
  ]
}));

const Vote = mongoose.model("Vote", new mongoose.Schema({
  ticket_id: String,
  candidate_id: String,
  gender: String,
  timestamp: Date
}));

const Candidate = mongoose.model("Candidate", new mongoose.Schema({
  name: String,
  description: String,
  photo: String,
  gender: String // "male" or "female"
}));

// === ROUTES ===

// Voting route
app.post("/vote", votingWindow, async (req, res) => {
  const { ticket_id, candidate_id, gender } = req.body;
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Manila" }); // YYYY-MM-DD

  try {
    const ticket = await Ticket.findOne({ ticket_id });
    if (!ticket) return res.status(400).json({ message: "Invalid ticket ID" });

    // Check if already voted today for this gender
    const alreadyUsed = ticket.used_dates.find(
      (u) => u.date === today && u.gender === gender
    );
    if (alreadyUsed) {
      return res.status(400).json({ message: `Already voted for ${gender} today` });
    }

    // Record vote
    const vote = new Vote({
      ticket_id,
      candidate_id,
      gender,
      timestamp: new Date()
    });
    await vote.save();

    // Update ticket usage
    ticket.used_dates.push({ date: today, gender });
    await ticket.save();

    res.json({ message: "Vote recorded successfully" });
  } catch (err) {
    res.status(500).json({ message: "Server error", error: err.message });
  }
});

// Candidate CRUD (simplified)
app.post("/candidates", async (req, res) => {
  const candidate = new Candidate(req.body);
  await candidate.save();
  res.json(candidate);
});

app.get("/candidates", async (req, res) => {
  const candidates = await Candidate.find();
  res.json(candidates);
});

// Admin login (hardcoded)
const admins = [
  { username: "admin1", password: "secret1" },
  { username: "admin2", password: "secret2" },
  { username: "admin3", password: "secret3" }
];

app.post("/admin/login", (req, res) => {
  const { username, password } = req.body;
  const match = admins.find(a => a.username === username && a.password === password);
  if (!match) return res.status(401).json({ message: "Invalid credentials" });
  res.json({ message: "Login successful" });
});

// Results (summary + audit logs)
app.get("/admin/results", async (req, res) => {
  const votes = await Vote.find();
  res.json(votes);
});

// === START SERVER ===
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));