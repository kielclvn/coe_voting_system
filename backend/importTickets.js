// backend/importTickets.js
const mongoose = require("mongoose");
const fs = require("fs");
const csv = require("csv-parser");

// === MongoDB Connection ===
const uri = "mongodb+srv://votingAdmin:secretPass@coevotingsystem.mhjm7sw.mongodb.net/coe_voting_system?retryWrites=true&w=majority";

mongoose.connect(uri)
  .then(() => console.log("MongoDB connected"))
  .catch(err => console.error("MongoDB connection error:", err));

// === Ticket Schema ===
const Ticket = mongoose.model("Ticket", new mongoose.Schema({
  ticket_id: String,
  section: String,
  type: String,
  status: String,
  used_dates: [
    {
      date: String,
      gender: String
    }
  ]
}));

// === Import Function ===
function importTickets(csvFilePath) {
  const tickets = [];
  fs.createReadStream(csvFilePath)
    .pipe(csv())
    .on("data", (row) => {
      tickets.push({
        ticket_id: row["Ticket ID"],   // map column name
        section: row["Section"],
        type: row["Type"],
        status: row["Status"],
        used_dates: []
      });
    })
    .on("end", async () => {
      try {
        await Ticket.insertMany(tickets);
        console.log("Tickets imported successfully!");
        mongoose.connection.close();
      } catch (err) {
        console.error("Error importing tickets:", err);
      }
    });
}

// === Run Import ===
importTickets("tickets.csv");