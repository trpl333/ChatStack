import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { insertLeadSchema } from "@shared/schema";
import { z } from "zod";

export async function registerRoutes(app: Express): Promise<Server> {
  app.get("/api/leads", async (req, res) => {
    try {
      const leads = await storage.getAllLeads();
      res.json(leads);
    } catch (error) {
      console.error("Error fetching leads:", error);
      res.status(500).json({ error: "Failed to fetch leads" });
    }
  });

  app.get("/api/leads/:id", async (req, res) => {
    try {
      const lead = await storage.getLeadById(req.params.id);
      if (!lead) {
        return res.status(404).json({ error: "Lead not found" });
      }
      res.json(lead);
    } catch (error) {
      console.error("Error fetching lead:", error);
      res.status(500).json({ error: "Failed to fetch lead" });
    }
  });

  app.post("/api/leads", async (req, res) => {
    try {
      const validatedData = insertLeadSchema.parse(req.body);
      const lead = await storage.createLead(validatedData);
      res.status(201).json(lead);
    } catch (error) {
      if (error instanceof z.ZodError) {
        return res.status(400).json({ error: "Invalid lead data", details: error.errors });
      }
      console.error("Error creating lead:", error);
      res.status(500).json({ error: "Failed to create lead" });
    }
  });

  app.post("/api/leads/:id/milestone", async (req, res) => {
    try {
      const { milestone } = req.body;
      if (!milestone) {
        return res.status(400).json({ error: "Milestone is required" });
      }
      
      const lead = await storage.toggleMilestone(req.params.id, milestone);
      res.json(lead);
    } catch (error) {
      if (error instanceof Error && error.message === "Lead not found") {
        return res.status(404).json({ error: "Lead not found" });
      }
      console.error("Error toggling milestone:", error);
      res.status(500).json({ error: "Failed to toggle milestone" });
    }
  });

  app.post("/api/leads/:id/mark-lost", async (req, res) => {
    try {
      const lead = await storage.markAsLost(req.params.id);
      res.json(lead);
    } catch (error) {
      if (error instanceof Error && error.message === "Lead not found") {
        return res.status(404).json({ error: "Lead not found" });
      }
      console.error("Error marking lead as lost:", error);
      res.status(500).json({ error: "Failed to mark lead as lost" });
    }
  });

  app.post("/api/leads/:id/reactivate", async (req, res) => {
    try {
      const lead = await storage.reactivateLead(req.params.id);
      res.json(lead);
    } catch (error) {
      if (error instanceof Error && error.message === "Lead not found") {
        return res.status(404).json({ error: "Lead not found" });
      }
      console.error("Error reactivating lead:", error);
      res.status(500).json({ error: "Failed to reactivate lead" });
    }
  });

  app.patch("/api/leads/:id/notes", async (req, res) => {
    try {
      const { notes } = req.body;
      if (typeof notes !== "string") {
        return res.status(400).json({ error: "Notes must be a string" });
      }
      
      const lead = await storage.updateLead(req.params.id, { notes });
      res.json(lead);
    } catch (error) {
      if (error instanceof Error && error.message === "Lead not found") {
        return res.status(404).json({ error: "Lead not found" });
      }
      console.error("Error updating notes:", error);
      res.status(500).json({ error: "Failed to update notes" });
    }
  });

  app.patch("/api/leads/:id/stage", async (req, res) => {
    try {
      const { stage } = req.body;
      if (!stage) {
        return res.status(400).json({ error: "Stage is required" });
      }
      
      const lead = await storage.updateLead(req.params.id, { 
        currentStage: stage,
        stageEnteredAt: new Date()
      });
      res.json(lead);
    } catch (error) {
      if (error instanceof Error && error.message === "Lead not found") {
        return res.status(404).json({ error: "Lead not found" });
      }
      console.error("Error updating stage:", error);
      res.status(500).json({ error: "Failed to update stage" });
    }
  });

  app.delete("/api/leads/:id", async (req, res) => {
    try {
      await storage.deleteLead(req.params.id);
      res.status(204).send();
    } catch (error) {
      if (error instanceof Error && error.message === "Lead not found") {
        return res.status(404).json({ error: "Lead not found" });
      }
      console.error("Error deleting lead:", error);
      res.status(500).json({ error: "Failed to delete lead" });
    }
  });

  const httpServer = createServer(app);

  return httpServer;
}
