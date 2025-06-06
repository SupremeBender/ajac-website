// signup_mission.js - extracted from signup_mission.html
console.log('[DEBUG] signup_mission.html main JS loaded');

document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('signup-root');
  if (!root) {
    console.error('[ERROR] #signup-root not found!');
    const errorDiv = document.createElement('div');
    errorDiv.textContent = 'Critical error: signup-root element is missing. Please reload or contact an admin.';
    errorDiv.style.color = 'red';
    errorDiv.style.fontWeight = 'bold';
    document.body.prepend(errorDiv);
    return;
  }
  const campaignId = root.dataset.campaignId || null;
  const persistentAcLocation = root.dataset.persistentAcLocation === 'true';

  if (!campaignId) {
    console.error('[ERROR] campaignId is missing! AJAX requests will fail.');
    const errorDiv = document.createElement('div');
    errorDiv.textContent = 'Critical error: campaign ID is missing. Please reload or contact an admin.';
    errorDiv.style.color = 'red';
    errorDiv.style.fontWeight = 'bold';
    document.body.prepend(errorDiv);
    return;
  }

  // Make persistentAcLocation available globally if needed
  window.persistentAcLocation = persistentAcLocation;

  // Define showClaimForm and hideClaimForm globally for template onclick
  window.showClaimForm = function(idx) {
    const form = document.getElementById('claim-form-' + idx);
    if (form) form.style.display = 'block';
  };
  window.hideClaimForm = function(idx) {
    const form = document.getElementById('claim-form-' + idx);
    if (form) form.style.display = 'none';
  };

    // Expand/collapse logic for flights
    document.querySelectorAll('.flight-collapsed-row').forEach(row => {
        row.addEventListener('click', function() {
            const group = row.closest('.flight-group');
            if (group) {
                group.classList.toggle('collapsed');
                const expanded = group.querySelector('.flight-expanded-content');
                if (expanded) {
                    expanded.style.display = group.classList.contains('collapsed') ? 'none' : 'block';
                    row.setAttribute('aria-expanded', !group.classList.contains('collapsed'));
                }
            }
        });
        // Keyboard accessibility: allow Enter/Space to toggle
        row.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                row.click();
            }
        });
    });

    // Close all flights button
    const closeAllBtn = document.getElementById('close-all-flights');
    if (closeAllBtn) {
        closeAllBtn.addEventListener('click', function() {
            document.querySelectorAll('.flight-group').forEach(group => {
                group.classList.add('collapsed');
                const expanded = group.querySelector('.flight-expanded-content');
                if (expanded) {
                    expanded.style.display = 'none';
                }
                const row = group.querySelector('.flight-collapsed-row');
                if (row) {
                    row.setAttribute('aria-expanded', false);
                }
            });
        });
    }

    // --- Dynamic dropdown logic for squadron, base, area, mission type, aircraft ---
    const squadronSelect = document.getElementById('squadron');
    const depBaseGroup = document.getElementById('depBaseGroup');
    const depBaseSelect = document.getElementById('departure_base');
    const recBaseGroup = document.getElementById('recBaseGroup');
    const recBaseSelect = document.getElementById('recovery_base');
    const areaGroup = document.getElementById('areaGroup');
    const areaSelect = document.getElementById('operations_area');
    const missionTypeGroup = document.getElementById('missionTypeGroup');
    const missionTypeSelect = document.getElementById('mission_type');
    const remarksGroup = document.getElementById('remarksGroup');
    const aircraftGroup = document.getElementById('aircraftGroup');
    const aircraftSelect = document.getElementById('aircraft_id');

    // Always show recovery base group if present
    if (recBaseGroup) recBaseGroup.style.display = '';

    function populateRecoveryBaseDropdown(selectedValue = null) {
        if (!recBaseSelect) return;
        recBaseSelect.innerHTML = '<option value="">Select recovery base</option>';
        if (window.basesData) {
            for (const [icao, baseObj] of Object.entries(window.basesData)) {
                const opt = document.createElement('option');
                opt.value = icao;
                opt.textContent = baseObj && baseObj.name ? baseObj.name : icao;
                recBaseSelect.appendChild(opt);
            }
        }
        if (selectedValue) recBaseSelect.value = selectedValue;
    }

    // Populate recovery base dropdown on page load
    populateRecoveryBaseDropdown();

    async function populateDepartureBaseDropdown() {
        if (!depBaseSelect || !squadronSelect.value) return;
        depBaseSelect.innerHTML = '<option value="">Select departure base</option>';
        try {
            const resp = await fetch("/signup/squadron-bases", {
                method: "POST",
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `squadron=${encodeURIComponent(squadronSelect.value)}&persistent=${persistentAcLocation ? '1' : '0'}&campaign_id=${encodeURIComponent(campaignId)}`
            });
            const data = await resp.json();
            console.log('[DEBUG] /signup/squadron-bases response:', data);
            if (data.bases && Array.isArray(data.bases)) {
                // If persistentAcLocation is true and only one base, restrict selection
                if (persistentAcLocation && data.bases.length === 1) {
                    const baseId = data.bases[0];
                    let baseName = baseId;
                    if (window.basesData && window.basesData[baseId] && window.basesData[baseId].name) {
                        baseName = window.basesData[baseId].name;
                    }
                    const opt = document.createElement('option');
                    opt.value = baseId;
                    opt.textContent = baseName;
                    depBaseSelect.appendChild(opt);
                    depBaseSelect.value = baseId;
                    depBaseSelect.disabled = true;
                } else {
                    depBaseSelect.disabled = false;
                    for (const baseId of data.bases) {
                        let baseName = baseId;
                        if (window.basesData && window.basesData[baseId] && window.basesData[baseId].name) {
                            baseName = window.basesData[baseId].name;
                        }
                        const opt = document.createElement('option');
                        opt.value = baseId;
                        opt.textContent = baseName;
                        depBaseSelect.appendChild(opt);
                    }
                }
            }
        } catch (e) {
            console.error('[ERROR] Could not fetch bases for squadron:', e);
        }
    }

    async function populateAircraftDropdown() {
        if (!aircraftSelect || !squadronSelect.value) return;
        aircraftSelect.innerHTML = '<option value="">Select aircraft</option>';
        try {
            const resp = await fetch("/signup/squadron-aircraft", {
                method: "POST",
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `squadron=${encodeURIComponent(squadronSelect.value)}&base=${encodeURIComponent(depBaseSelect.value)}&persistent=${persistentAcLocation ? '1' : '0'}&campaign_id=${encodeURIComponent(campaignId)}&mode=lead`
            });
            const data = await resp.json();
            console.log('[DEBUG] /signup/squadron-aircraft response:', data);
            let found = false;
            if (data.aircraft && Array.isArray(data.aircraft)) {
                for (const ac of data.aircraft) {
                    const opt = document.createElement('option');
                    opt.value = ac.tail;
                    opt.textContent = `${ac.type} (${ac.tail}) - ${ac.location}`;
                    opt.setAttribute('data-location', ac.location);
                    aircraftSelect.appendChild(opt);
                    found = true;
                }
            }
            if (!found) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'No aircraft available for this squadron/base';
                aircraftSelect.appendChild(opt);
            }
        } catch (e) {
            console.error('[ERROR] Could not fetch aircraft for squadron:', e);
        }
    }

    if (squadronSelect) {
        squadronSelect.addEventListener('change', function() {
            if (squadronSelect.value) {
                depBaseGroup.style.display = '';
                populateDepartureBaseDropdown().then(() => {
                    populateAircraftDropdown();
                    // Always repopulate recovery base dropdown on squadron change
                    populateRecoveryBaseDropdown();
                });
            } else {
                depBaseGroup.style.display = 'none';
                areaGroup.style.display = 'none';
                missionTypeGroup.style.display = 'none';
                remarksGroup.style.display = 'none';
                aircraftGroup.style.display = 'none';
                // Do not hide recBaseGroup, just clear it
                populateRecoveryBaseDropdown();
            }
        });
    }
    if (depBaseSelect) {
        depBaseSelect.addEventListener('change', function() {
            // Always show and repopulate recovery base dropdown
            populateRecoveryBaseDropdown();
            if (depBaseSelect.value) {
                // ...existing code...
            } else {
                areaGroup.style.display = 'none';
                missionTypeGroup.style.display = 'none';
                remarksGroup.style.display = 'none';
                aircraftGroup.style.display = 'none';
            }
            populateAircraftDropdown();
        });
    }

    if (recBaseSelect) {
        recBaseSelect.addEventListener('change', function() {
            if (recBaseSelect.value) {
                if (campaignType === "TR") {
                    areaGroup.style.display = '';
                } else {
                    areaGroup.style.display = 'none';
                    missionTypeGroup.style.display = '';
                }
            } else {
                areaGroup.style.display = 'none';
                missionTypeGroup.style.display = 'none';
                remarksGroup.style.display = 'none';
                aircraftGroup.style.display = 'none';
            }
        });
    }
    if (areaSelect) {
        areaSelect.addEventListener('change', function() {
            if (areaSelect.value) {
                missionTypeGroup.style.display = '';
            } else {
                missionTypeGroup.style.display = 'none';
                remarksGroup.style.display = 'none';
                aircraftGroup.style.display = 'none';
            }
        });
    }
    if (missionTypeSelect) {
        missionTypeSelect.addEventListener('change', function() {
            if (missionTypeSelect.value) {
                remarksGroup.style.display = '';
                aircraftGroup.style.display = '';
                populateAircraftDropdown();
            } else {
                remarksGroup.style.display = 'none';
                aircraftGroup.style.display = 'none';
            }
        });
    }

    document.querySelectorAll('.join-pos-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const flightId = btn.getAttribute('data-flight-id');
            const squadron = btn.getAttribute('data-squadron');
            const base = btn.getAttribute('data-base');
            const pos = btn.getAttribute('data-position');
            document.querySelectorAll('.join-flight-form').forEach(f => f.style.display = 'none');
            const formDiv = document.getElementById('join-form-' + flightId + '-' + pos);
            if (formDiv) {
                formDiv.style.display = 'block';
                const acSelect = document.getElementById('aircraft_id_' + flightId + '_' + pos);
                if (acSelect) {
                    acSelect.innerHTML = '<option value="">Loading aircraft...</option>';
                    fetch("/signup/squadron-aircraft", {
                        method: "POST",
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: `squadron=${encodeURIComponent(squadron)}&campaign_id=${encodeURIComponent(campaignId)}&mode=wingman`
                    })
                    .then(resp => resp.json())
                    .then(data => {
                        console.log(`[DEBUG] [Join] /signup/squadron-aircraft response for squadron ${squadron}:`, data);
                        acSelect.innerHTML = '<option value="">Select aircraft</option>';
                        let found = false;
                        if (data.aircraft && Array.isArray(data.aircraft)) {
                            for (const ac of data.aircraft) {
                                const opt = document.createElement('option');
                                opt.value = ac.tail;
                                opt.textContent = `${ac.type} (${ac.tail}) - ${ac.location}`;
                                opt.setAttribute('data-location', ac.location);
                                acSelect.appendChild(opt);
                                found = true;
                            }
                        }
                        if (!found) {
                            const opt = document.createElement('option');
                            opt.value = '';
                            opt.textContent = 'No aircraft available for this squadron';
                            acSelect.appendChild(opt);
                        }
                    })
                    .catch(err => {
                        console.error('[ERROR] Could not fetch aircraft for squadron:', err);
                    });
                }
                acSelect && acSelect.addEventListener('change', function() {
                    const selected = acSelect.options[acSelect.selectedIndex];
                    const acLoc = selected ? selected.getAttribute('data-location') : null;
                    const warning = document.getElementById('cross-base-warning-' + flightId + '-' + pos);
                    if (acLoc && acLoc !== base) {
                        warning.style.display = '';
                    } else {
                        warning.style.display = 'none';
                    }
                });
            }
        });
    });
    document.querySelectorAll('.cancel-join-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const flightId = btn.getAttribute('data-flight-id');
            const pos = btn.getAttribute('data-position');
            const formDiv = document.getElementById('join-form-' + flightId + '-' + pos);
            if (formDiv) formDiv.style.display = 'none';
        });
    });

    document.querySelectorAll('.squadron-select').forEach(squadronSelect => {
        squadronSelect.addEventListener('change', async function() {
            const formId = this.id.split('_').pop();
            const baseSelect = document.getElementById(`departure_base_${formId}`);
            const aircraftSelect = document.getElementById(`aircraft_id_${formId}`);
            if (!baseSelect || !aircraftSelect) return;
            baseSelect.innerHTML = '<option value="">Select departure base</option>';
            aircraftSelect.innerHTML = '<option value="">Select aircraft</option>';
            if (!this.value) return;
            try {
                // Only show valid bases for persistent location
                const resp = await fetch("/signup/squadron-bases", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `squadron=${encodeURIComponent(this.value)}&persistent=${persistentAcLocation ? '1' : '0'}&campaign_id=${encodeURIComponent(campaignId)}`
                });
                const data = await resp.json();
                if (data.bases && Array.isArray(data.bases)) {
                    for (const baseId of data.bases) {
                        let baseName = baseId;
                        if (window.basesData && window.basesData[baseId] && window.basesData[baseId].name) {
                            baseName = window.basesData[baseId].name;
                        }
                        const opt = document.createElement('option');
                        opt.value = baseId;
                        opt.textContent = baseName;
                        baseSelect.appendChild(opt);
                    }
                }
            } catch (e) {
                console.error('[ERROR] Could not fetch bases for squadron:', e);
            }
            try {
                const resp2 = await fetch("/signup/squadron-aircraft", {
                    method: "POST",
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `squadron=${encodeURIComponent(this.value)}&campaign_id=${encodeURIComponent(campaignId)}&mode=lead`
                });
                const data2 = await resp2.json();
                if (data2.aircraft && Array.isArray(data2.aircraft)) {
                    for (const ac of data2.aircraft) {
                        const opt = document.createElement('option');
                        opt.value = ac.tail;
                        opt.textContent = `${ac.type} (${ac.tail}) - ${ac.location}`;
                        aircraftSelect.appendChild(opt);
                    }
                }
            } catch (e) {
                console.error('[ERROR] Could not fetch aircraft for squadron:', e);
            }
        });
    });

    // --- Curated slot claim: Area/mission type logic ---
    document.querySelectorAll('.curated-slot-form').forEach(form => {
        const areaGroup = form.querySelector('.area-group');
        const missionTypeGroup = form.querySelector('.mission-type-group');
        if (form.dataset.campaigntype === 'OP') {
            if (areaGroup) areaGroup.style.display = 'none';
            if (missionTypeGroup) missionTypeGroup.style.display = '';
        } else {
            if (areaGroup) areaGroup.style.display = '';
            if (missionTypeGroup) missionTypeGroup.style.display = '';
        }
    });

    // Utility: Format nickname (capitalize, remove tags)
    function formatNickname(nick) {
        if (!nick) return '';
        // Remove Discord tags (e.g., #1234)
        let clean = nick.replace(/#\d{4,}/, '');
        // Capitalize first letter, lower the rest
        clean = clean.trim();
        if (clean.length > 0) {
            clean = clean[0].toUpperCase() + clean.slice(1);
        }
        return clean;
    }

    // Utility: Update pilot info display in current flights list
    function updatePilotInfoDisplay(flightId, position, pilot) {
        // Find the pilot info row by flightId and position
        const pilotRow = document.querySelector(`#flight-pilot-row-${flightId}-${position}`);
        if (!pilotRow || !pilot) return;
        // Update nickname, tail, squawk, and transponder
        const nickCell = pilotRow.querySelector('.pilot-nickname');
        const tailCell = pilotRow.querySelector('.pilot-tail');
        const squawkCell = pilotRow.querySelector('.pilot-squawk');
        const transponderCell = pilotRow.querySelector('.pilot-transponder');
        if (nickCell) nickCell.textContent = formatNickname(pilot.nickname);
        if (tailCell) tailCell.textContent = pilot.aircraft_id || '';
        if (squawkCell) squawkCell.textContent = pilot.squawk || '';
        if (transponderCell) transponderCell.textContent = pilot.transponder || '';
    }

    // Utility: Clear callsign for curated slot when pilot leaves
    function clearCuratedSlotCallsign(slotId) {
        // Find the slot row and clear callsign cell
        const slotRow = document.querySelector(`#curated-slot-row-${slotId}`);
        if (!slotRow) return;
        const callsignCell = slotRow.querySelector('.slot-callsign');
        if (callsignCell) callsignCell.textContent = '';
    }

    // Listen for custom events from backend or AJAX (if used)
    document.addEventListener('pilotInfoUpdated', function(e) {
        // e.detail = { flightId, position, pilot }
        if (e.detail && e.detail.flightId && e.detail.position && e.detail.pilot) {
            updatePilotInfoDisplay(e.detail.flightId, e.detail.position, e.detail.pilot);
        }
    });
    document.addEventListener('curatedSlotRestored', function(e) {
        // e.detail = { slotId }
        if (e.detail && e.detail.slotId) {
            clearCuratedSlotCallsign(e.detail.slotId);
        }
    });
});
// End signup_mission.js
