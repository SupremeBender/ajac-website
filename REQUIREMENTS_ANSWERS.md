# AJAC DCS Mission Planner - Requirements Answers

## PRIORITY & CRITICAL RESPONSES

### Q10.4 - Priority Ranking (1=highest, 5=lowest):
1. **Fix critical production bugs** - Priority 1
2. **Improve performance** - Priority 2  
3. **Add new features** - Priority 3
4. **Better user interface** - Priority 4
5. **Improve security** - Priority 5

### Q1.1 - Primary Purpose:
**Primary tool for planning campaigns and missions for a large DCS group**

**Short-term goals:**
- Function as signup sheet with automatic callsign assignment
- Easy overview for mission makers
- Close Discord integration
- Track aircraft locations for realism/roleplay

**Medium-term goals:**
- Allow players/flight leads to plan missions
- Auto-generate Mission Data Cards and kneeboard items
- Automate time-consuming tasks without over-constraining

**Long-term goals:**
- Direct DCS .miz file integration
- API integrations with other programs

### Q1.4 - User Roles:
- **ADMIN**: Top-level changes, administrate missions/campaigns
- **MISSION MAKER**: Full control over campaigns/missions parameters
- **PILOTS**: Sign up to missions, participate in planning
  - Blue side vs Red side (via Discord roles from config)
  - No sub-roles needed initially (flight leads, wingmen, squad leaders can come later)

### Q2.1 - Campaign Definition:
- **Specific exercise or operation** (finite campaigns)
- **Running training campaigns** that never end or reset yearly
- Example: "AJAC Training Campaign 2025" → "AJAC Training Campaign 2026"
- **Always stay in 1 theatre** per campaign

### Q4.1 - Authentication:
- **Stick with Discord OAuth only**
- Leverage existing community, role system, and bots
- Plan to flesh out Discord bot integration

---

## IMMEDIATE ACTION PLAN
Based on Priority 1 (Fix critical bugs), we need to:

1. **Fix TypeError in signup/routes.py line 187** (causing 500 errors)
2. **Add missing imports in models/flight.py** (json, os, logging, uuid, traceback)
3. **Create missing config.py** referenced by app.py
4. **Handle data format migration** (old "members" vs new "pilots" format)

Ready to proceed with emergency fixes!
