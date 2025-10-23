import { sql } from "drizzle-orm";
import { pgTable, text, varchar, timestamp, jsonb } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const leadStages = [
  "First Contact",
  "Follow-up",
  "Quote Sent",
  "Application",
  "Underwriting",
  "Closed/Bound",
  "Lost"
] as const;

export type LeadStage = typeof leadStages[number];

export type MilestoneHistory = {
  stage: LeadStage;
  completedAt: string;
}[];

export const leads = pgTable("leads", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  company: text("company").notNull(),
  phone: text("phone").notNull(),
  email: text("email").notNull(),
  source: text("source").notNull(),
  currentStage: text("current_stage").notNull().default("First Contact"),
  completedMilestones: text("completed_milestones").array().notNull().default(sql`ARRAY[]::text[]`),
  milestoneHistory: jsonb("milestone_history").$type<MilestoneHistory>().default(sql`'[]'::jsonb`),
  notes: text("notes").default(""),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
  stageEnteredAt: timestamp("stage_entered_at").notNull().defaultNow(),
});

export const insertLeadSchema = createInsertSchema(leads).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
  stageEnteredAt: true,
}).extend({
  name: z.string().min(1, "Name is required"),
  company: z.string().min(1, "Company is required"),
  phone: z.string().min(1, "Phone is required"),
  email: z.string().email("Valid email is required"),
  source: z.string().min(1, "Source is required"),
});

export type InsertLead = z.infer<typeof insertLeadSchema>;
export type Lead = typeof leads.$inferSelect;

export const users = pgTable("users", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
});

export const insertUserSchema = createInsertSchema(users).pick({
  username: true,
  password: true,
});

export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = typeof users.$inferSelect;
