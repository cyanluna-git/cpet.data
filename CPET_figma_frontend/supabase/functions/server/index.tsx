import { Hono } from "npm:hono";
import { cors } from "npm:hono/cors";
import { logger } from "npm:hono/logger";
import * as kv from "./kv_store.tsx";
import { createClient } from "jsr:@supabase/supabase-js@2";

const app = new Hono();

// Initialize Supabase client
const supabase = createClient(
  Deno.env.get('SUPABASE_URL') ?? '',
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
);

// Enable logger
app.use('*', logger(console.log));

// Enable CORS for all routes and methods
app.use(
  "/*",
  cors({
    origin: "*",
    allowHeaders: ["Content-Type", "Authorization"],
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    exposeHeaders: ["Content-Length"],
    maxAge: 600,
  }),
);

// ========== AUTHENTICATION ROUTES ==========

// Sign up (Admin only - creates new users)
app.post("/make-server-3f6fd63f/auth/signup", async (c) => {
  try {
    const { email, password, name, role, subjectInfo } = await c.req.json();

    // Create user with Supabase Auth
    const { data: authData, error: authError } = await supabase.auth.admin.createUser({
      email,
      password,
      email_confirm: true, // Auto-confirm since email server not configured
      user_metadata: { name, role }
    });

    if (authError) {
      console.log(`Signup error: ${authError.message}`);
      return c.json({ error: authError.message }, 400);
    }

    // Store user profile in KV
    await kv.set(`user:${authData.user.id}`, {
      id: authData.user.id,
      email,
      name,
      role,
      created_at: new Date().toISOString()
    });

    // If role is 'subject', create subject profile
    if (role === 'subject' && subjectInfo) {
      const subjectId = crypto.randomUUID();
      await kv.set(`subject:${subjectId}`, {
        id: subjectId,
        user_id: authData.user.id,
        research_id: `SUB-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 1000)).padStart(3, '0')}`,
        name: subjectInfo.name || name,
        birth_year: subjectInfo.birth_year,
        gender: subjectInfo.gender,
        height_cm: subjectInfo.height_cm,
        weight_kg: subjectInfo.weight_kg,
        created_at: new Date().toISOString()
      });

      await kv.set(`user_subject:${authData.user.id}`, subjectId);
    }

    return c.json({ 
      success: true,
      user: {
        id: authData.user.id,
        email,
        role
      }
    });
  } catch (error) {
    console.log(`Signup error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Get current user info
app.get("/make-server-3f6fd63f/auth/me", async (c) => {
  try {
    const authHeader = c.req.header('Authorization');
    if (!authHeader) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const token = authHeader.split(' ')[1];
    const { data: { user }, error } = await supabase.auth.getUser(token);

    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const userProfile = await kv.get(`user:${user.id}`);
    
    return c.json({
      id: user.id,
      email: user.email,
      ...userProfile,
    });
  } catch (error) {
    console.log(`Auth check error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// ========== SUBJECT ROUTES ==========

// Get all subjects (Researcher/Admin only)
app.get("/make-server-3f6fd63f/subjects", async (c) => {
  try {
    const subjects = await kv.getByPrefix('subject:');
    return c.json(subjects.map(s => s.value));
  } catch (error) {
    console.log(`Get subjects error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Get single subject
app.get("/make-server-3f6fd63f/subjects/:id", async (c) => {
  try {
    const id = c.req.param('id');
    const subject = await kv.get(`subject:${id}`);
    
    if (!subject) {
      return c.json({ error: 'Subject not found' }, 404);
    }

    // Get tests for this subject
    const allTests = await kv.getByPrefix('test:');
    const subjectTests = allTests
      .map(t => t.value)
      .filter(test => test.subject_id === id)
      .sort((a, b) => new Date(b.test_date) - new Date(a.test_date));

    return c.json({
      ...subject,
      tests: subjectTests
    });
  } catch (error) {
    console.log(`Get subject error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Create subject
app.post("/make-server-3f6fd63f/subjects", async (c) => {
  try {
    const subjectData = await c.req.json();
    const subjectId = crypto.randomUUID();
    
    const subject = {
      id: subjectId,
      research_id: `SUB-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 1000)).padStart(3, '0')}`,
      ...subjectData,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    await kv.set(`subject:${subjectId}`, subject);
    return c.json(subject);
  } catch (error) {
    console.log(`Create subject error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// ========== TEST ROUTES ==========

// Get all tests
app.get("/make-server-3f6fd63f/tests", async (c) => {
  try {
    const tests = await kv.getByPrefix('test:');
    return c.json(tests.map(t => t.value).sort((a, b) => 
      new Date(b.test_date) - new Date(a.test_date)
    ));
  } catch (error) {
    console.log(`Get tests error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Get single test with full data
app.get("/make-server-3f6fd63f/tests/:id", async (c) => {
  try {
    const id = c.req.param('id');
    const test = await kv.get(`test:${id}`);
    
    if (!test) {
      return c.json({ error: 'Test not found' }, 404);
    }

    // Get subject info
    const subject = await kv.get(`subject:${test.subject_id}`);

    return c.json({
      ...test,
      subject
    });
  } catch (error) {
    console.log(`Get test error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Create test
app.post("/make-server-3f6fd63f/tests", async (c) => {
  try {
    const testData = await c.req.json();
    const testId = crypto.randomUUID();
    
    const test = {
      id: testId,
      ...testData,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    await kv.set(`test:${testId}`, test);
    return c.json(test);
  } catch (error) {
    console.log(`Create test error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Update test
app.put("/make-server-3f6fd63f/tests/:id", async (c) => {
  try {
    const id = c.req.param('id');
    const updates = await c.req.json();
    
    const existing = await kv.get(`test:${id}`);
    if (!existing) {
      return c.json({ error: 'Test not found' }, 404);
    }

    const updated = {
      ...existing,
      ...updates,
      updated_at: new Date().toISOString()
    };

    await kv.set(`test:${id}`, updated);
    return c.json(updated);
  } catch (error) {
    console.log(`Update test error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Delete test
app.delete("/make-server-3f6fd63f/tests/:id", async (c) => {
  try {
    const id = c.req.param('id');
    await kv.del(`test:${id}`);
    return c.json({ success: true });
  } catch (error) {
    console.log(`Delete test error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// ========== STATISTICS ROUTES ==========

// Get cohort statistics
app.post("/make-server-3f6fd63f/cohort/stats", async (c) => {
  try {
    const { filters } = await c.req.json();
    
    const allTests = await kv.getByPrefix('test:');
    const allSubjects = await kv.getByPrefix('subject:');
    
    // Filter subjects based on criteria
    let filteredSubjects = allSubjects.map(s => s.value);
    
    if (filters.gender) {
      filteredSubjects = filteredSubjects.filter(s => s.gender === filters.gender);
    }
    
    if (filters.age_min || filters.age_max) {
      const currentYear = new Date().getFullYear();
      filteredSubjects = filteredSubjects.filter(s => {
        const age = currentYear - s.birth_year;
        return (!filters.age_min || age >= filters.age_min) &&
               (!filters.age_max || age <= filters.age_max);
      });
    }

    // Get tests for filtered subjects
    const subjectIds = new Set(filteredSubjects.map(s => s.id));
    const filteredTests = allTests
      .map(t => t.value)
      .filter(test => subjectIds.has(test.subject_id));

    // Calculate statistics
    const vo2MaxValues = filteredTests
      .map(t => t.summary?.vo2_max_rel)
      .filter(v => v != null);
    
    const fatMaxHrValues = filteredTests
      .map(t => t.summary?.fat_max_hr)
      .filter(v => v != null);

    const calculateStats = (values) => {
      if (values.length === 0) return null;
      
      values.sort((a, b) => a - b);
      const sum = values.reduce((a, b) => a + b, 0);
      const mean = sum / values.length;
      const median = values[Math.floor(values.length / 2)];
      
      return {
        mean,
        median,
        min: values[0],
        max: values[values.length - 1],
        p10: values[Math.floor(values.length * 0.1)],
        p25: values[Math.floor(values.length * 0.25)],
        p75: values[Math.floor(values.length * 0.75)],
        p90: values[Math.floor(values.length * 0.9)],
        count: values.length
      };
    };

    return c.json({
      sample_size: filteredSubjects.length,
      test_count: filteredTests.length,
      vo2_max_stats: calculateStats(vo2MaxValues),
      fat_max_hr_stats: calculateStats(fatMaxHrValues),
      subjects: filteredSubjects,
      tests: filteredTests
    });
  } catch (error) {
    console.log(`Cohort stats error: ${error.message}`);
    return c.json({ error: error.message }, 500);
  }
});

// Health check endpoint
app.get("/make-server-3f6fd63f/health", (c) => {
  return c.json({ status: "ok" });
});

Deno.serve(app.fetch);