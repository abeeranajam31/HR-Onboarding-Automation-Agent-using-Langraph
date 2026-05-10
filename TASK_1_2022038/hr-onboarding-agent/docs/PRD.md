# Product Requirements Document (PRD)
## HR Onboarding Automation Agent

### Problem Statement
**Current Bottleneck:**
HR teams manually coordinate onboarding across 5+ systems (email, equipment, training, payroll, calendar). For a company hiring 20+ people/month, this creates:
- 8-12 hours of manual work per new hire
- Missed tasks leading to poor Day 1 experience
- Delayed equipment causing productivity loss
- Compliance risks from incomplete training

**What We're Solving:**
Automate the repetitive coordination work, allowing HR to focus on human connection while the agent handles system integration and task tracking.

### User Personas

**Primary User: HR Coordinator **
- Age: 28-35
- Role: Manages onboarding for 50-100 employees/year
- Pain Points: Juggling spreadsheets, forgetting follow-ups, manual data entry
- Goal: Zero Day 1 failures, more time for employee relationships

**Secondary User: New Hire **
- Expectations: Seamless experience, clear communication, equipment ready
- Frustration: Waiting days for access, unclear next steps

**Stakeholder: IT Manager **
- Needs: Automated provisioning, reduced ticket volume
- Concern: Security compliance, proper access controls

### Success Metrics

**Efficiency Metrics:**
- ⏱️ Reduce onboarding coordination time from 10 hours → 2 hours per hire
- 📉 Decrease IT support tickets by 40% (fewer "I don't have access" requests)
- ⚡ Equipment ordered within 24 hours of offer acceptance (vs. 3-5 days manual)

**Quality Metrics:**
- ✅ 100% task completion rate (no missed steps)
- 🎯 95%+ Day 1 readiness score (all systems accessible)
- 📊 Compliance training completion: 100% before start date

**Experience Metrics:**
- 😊 New hire satisfaction score: 4.5+/5
- 🔄 HR team reports 60%+ time savings
- 📧 Reduced back-and-forth emails by 70%

### Agent Capabilities

**PERCEIVE:**
- Monitor HR database for new hires
- Read onboarding policy documents
- Check equipment inventory status
- Track training completion via LMS API
- Monitor calendar availability

**REASON:**
- Determine role-specific requirements
- Calculate optimal task sequencing
- Handle exceptions (equipment delays, missing documents)
- Prioritize urgent vs. routine tasks
- Decide when to escalate to humans

**EXECUTE:**
- Create email accounts
- Order equipment from inventory
- Assign training modules
- Schedule orientation meetings
- Send automated notifications
- Update tracking dashboards

## Project Tools

This project includes HR onboarding tools with Pydantic validation, integrated into a ReAct agent:

1. **search_onboarding_knowledge** – Search HR policies and onboarding docs. Input: `query`, optional `doc_type`, `top_k`. Returns top relevant documents.

2. **generate_onboarding_checklist** – Generate a task checklist for a new hire. Input: `role`, `department`, `start_date`. Returns tasks with urgency labels (`OVERDUE`, `URGENT`, `UPCOMING`).

3. **get_employee_onboarding_status** – Retrieve employee profile and start date. Input: `employee_id`. Returns role, department, start date, and days until start.

4. **evaluate_day1_readiness** – Assess Day-1 readiness. Input: `employee_id`. Returns readiness score (`READY`, `AT RISK`, `NOT READY`) with blockers.

5. **calculate_onboarding_risk** – Calculate onboarding delay risk. Input: `employee_id`. Returns numeric score (0–100) and risk level (`LOW`, `MEDIUM`, `HIGH`).

All tools allow the agent to reason, call the appropriate tool, and update its state with real data.
