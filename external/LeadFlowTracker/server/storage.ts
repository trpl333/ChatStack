import { type Lead, type InsertLead, leadStages, type LeadStage, leads } from "@shared/schema";
import { randomUUID } from "crypto";
import { syncLeadToSheet, syncAllLeadsToSheet } from "./sheetService";
import { db } from "./db";
import { eq, desc } from "drizzle-orm";

export interface IStorage {
  getAllLeads(): Promise<Lead[]>;
  getLeadById(id: string): Promise<Lead | undefined>;
  createLead(lead: InsertLead): Promise<Lead>;
  updateLead(id: string, updates: Partial<Lead>): Promise<Lead>;
  toggleMilestone(id: string, milestone: LeadStage): Promise<Lead>;
  markAsLost(id: string): Promise<Lead>;
  reactivateLead(id: string): Promise<Lead>;
  deleteLead(id: string): Promise<void>;
}

export class DbStorage implements IStorage {
  async getAllLeads(): Promise<Lead[]> {
    return await db.select().from(leads).orderBy(desc(leads.createdAt));
  }

  async getLeadById(id: string): Promise<Lead | undefined> {
    const result = await db.select().from(leads).where(eq(leads.id, id));
    return result[0];
  }

  async createLead(insertLead: InsertLead): Promise<Lead> {
    const now = new Date();
    
    const newLead = {
      ...insertLead,
      currentStage: "First Contact" as const,
      completedMilestones: [],
      notes: insertLead.notes || "",
      createdAt: now,
      updatedAt: now,
      stageEnteredAt: now,
    };
    
    const result = await db.insert(leads).values(newLead as any).returning();
    const lead = result[0];
    
    try {
      await syncLeadToSheet(lead);
    } catch (error) {
      console.error("Failed to sync lead to sheet:", error);
    }
    
    return lead;
  }

  async updateLead(id: string, updates: Partial<Lead>): Promise<Lead> {
    const existingLead = await this.getLeadById(id);
    if (!existingLead) {
      throw new Error("Lead not found");
    }

    const result = await db
      .update(leads)
      .set({ ...updates, updatedAt: new Date() })
      .where(eq(leads.id, id))
      .returning();
    
    const updatedLead = result[0];
    
    try {
      await syncLeadToSheet(updatedLead);
    } catch (error) {
      console.error("Failed to sync lead to sheet:", error);
    }
    
    return updatedLead;
  }

  async toggleMilestone(id: string, milestone: LeadStage): Promise<Lead> {
    const lead = await this.getLeadById(id);
    if (!lead) {
      throw new Error("Lead not found");
    }

    if (milestone === "Lost") {
      return this.markAsLost(id);
    }

    const completedMilestones = lead.completedMilestones || [];
    const milestoneHistory = lead.milestoneHistory || [];
    const milestoneIndex = leadStages.indexOf(milestone);
    
    const isCompleted = completedMilestones.includes(milestone);

    let newCompletedMilestones: string[];
    let newCurrentStage: string;
    let newMilestoneHistory = [...milestoneHistory];

    if (isCompleted) {
      newCompletedMilestones = completedMilestones.filter(m => m !== milestone);
      newMilestoneHistory = milestoneHistory.filter(h => h.stage !== milestone);
      
      const progressMilestones = leadStages.filter(s => s !== "Lost");
      const previousMilestones = progressMilestones.slice(0, milestoneIndex);
      const lastCompleted = previousMilestones.reverse().find(m => 
        newCompletedMilestones.includes(m)
      );
      newCurrentStage = lastCompleted || leadStages[0];
    } else {
      newCompletedMilestones = [...completedMilestones, milestone];
      newMilestoneHistory.push({
        stage: milestone,
        completedAt: new Date().toISOString(),
      });
      
      const progressMilestones = leadStages.filter(s => s !== "Lost");
      const nextMilestoneIndex = progressMilestones.indexOf(milestone) + 1;
      if (nextMilestoneIndex < progressMilestones.length) {
        newCurrentStage = progressMilestones[nextMilestoneIndex];
      } else {
        newCurrentStage = milestone;
      }
    }

    return this.updateLead(id, {
      completedMilestones: newCompletedMilestones,
      milestoneHistory: newMilestoneHistory,
      currentStage: newCurrentStage,
      stageEnteredAt: newCurrentStage !== lead.currentStage ? new Date() : lead.stageEnteredAt,
    });
  }

  async markAsLost(id: string): Promise<Lead> {
    const lead = await this.getLeadById(id);
    if (!lead) {
      throw new Error("Lead not found");
    }

    return this.updateLead(id, {
      currentStage: "Lost",
      stageEnteredAt: new Date(),
    });
  }

  async reactivateLead(id: string): Promise<Lead> {
    const lead = await this.getLeadById(id);
    if (!lead) {
      throw new Error("Lead not found");
    }

    if (lead.currentStage !== "Lost") {
      return lead;
    }

    const completedMilestones = lead.completedMilestones || [];
    const progressMilestones = leadStages.filter(s => s !== "Lost");
    
    const lastCompleted = [...progressMilestones].reverse().find(m => 
      completedMilestones.includes(m)
    );
    
    if (lastCompleted) {
      const lastCompletedIndex = progressMilestones.indexOf(lastCompleted);
      const nextIndex = lastCompletedIndex + 1;
      const newCurrentStage = nextIndex < progressMilestones.length 
        ? progressMilestones[nextIndex]
        : lastCompleted;
      
      return this.updateLead(id, {
        currentStage: newCurrentStage,
        stageEnteredAt: new Date(),
      });
    }
    
    return this.updateLead(id, {
      currentStage: leadStages[0],
      stageEnteredAt: new Date(),
    });
  }

  async deleteLead(id: string): Promise<void> {
    const lead = await this.getLeadById(id);
    if (!lead) {
      throw new Error("Lead not found");
    }

    await db.delete(leads).where(eq(leads.id, id));
  }
}

export const storage = new DbStorage();
