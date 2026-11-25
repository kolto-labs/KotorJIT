# KotorJIT Lua API (complete reference)

This file documents the runtime Lua surface. Routine tables are generated from `data/routines/*.json`; regenerate this document when those signatures change.

## Automatic loading

At game startup the proxy scans `<game>/kotorjit/scripts/*.lua` (top-level files, lexical order) and loads each file once. Create the directory and drop files there; no `.nss` compiler or registration file is required. Set `priority = 10` in a file to order callbacks (higher first; filename breaks ties). `OnScriptLoad(game, build)` runs after loading. Reload/unload invokes `OnScriptUnload`. Errors quarantine the offending script.

Example:
```lua
priority = 100
function OnScriptLoad(game, build) kp.print("loaded " .. game .. " " .. build) end
function OnTick(tick) end
```

The loader is invoked by the game startup sequence; it is not the harness channel. To enable the optional control channel, set `harness_port=27015` and `harness_bind=127.0.0.1` in `kotorjit.ini` (or `KOTORJIT_HARNESS_PORT`).

## Core Lua modules

### `nwscript`

`nwscript.call(name, ...)` is the only direct NWScript routine entry point. Routine names are not exported as Lua globals or table members. Arguments and return types follow the tables below. Object IDs are unsigned 32-bit engine handles; `0`/`0xffffffff` have routine-specific meanings. Optional parameters may be omitted when the signature marks a default.

### `kp`

All native host facilities live below this root. API version 2 removes the old
host root, bare host names, underscored aliases, and the global event/identity
tables. See [the migration reference](api-dialects.md). Standard Lua `print` is
unchanged; use `kp.print` for runtime logging or captured console/harness output.
Register callbacks with `kp.events.register(kp.events.OnTick, handler)` and remove
them with `kp.events.unregister`. Global `On*` discovery remains a documented
legacy behavior of the dispatcher; script-defined `priority` still orders handlers.

- `nwscript.with_caller(object_id, function)` temporarily supplies the engine caller (`OBJECT_SELF`) while the closure runs, then restores it even on error. Use it for action routines.
- `kp.registertimer(milliseconds, "callback_name"[, data])` schedules a Lua callback on the game thread.
- `kp.diagnostic(text[, level])`, `kp.console(text)`, and `kp.feedback(text[, x, y[, life]])` write diagnostics.
- `kp.mem.readbyte/readword/readdword/readfloat/readstring`, corresponding writes, and `kp.mem.findsig(pattern)` provide explicitly unsafe process-memory access; prefer named routines and validate addresses.
- `kp.struct` exposes supported engine structures; K2 support remains build-dependent.

### Callback events

See `docs/lua-api.md` for the generated event callback contract. Callback names currently include `OnScriptLoad`, `OnScriptUnload`, `OnConsoleCommand`, `OnRunScript`, `OnRunScriptDone`, `OnTick`, `OnDialogConditional`, and creature/area/item/module events. Return `false` from a cancellable callback to stop the game handler; return nothing to abstain.

## Generated routine catalog: K1

772 signatures (`data/routines/k1.json`).

| ID | Routine name | Returns | Parameters |
|---:|---|---|---|
| 0 | `Random` | `int` | int nMaxInteger |
| 1 | `PrintString` | `void` | string sString |
| 2 | `PrintFloat` | `void` | float fFloat, int nWidth=18, int nDecimals=9 |
| 3 | `FloatToString` | `string` | float fFloat, int nWidth=18, int nDecimals=9 |
| 4 | `PrintInteger` | `void` | int nInteger |
| 5 | `PrintObject` | `void` | object oObject |
| 6 | `AssignCommand` | `void` | object oActionSubject, action aActionToAssign |
| 7 | `DelayCommand` | `void` | float fSeconds, action aActionToDelay |
| 8 | `ExecuteScript` | `void` | string sScript, object oTarget, int nScriptVar=-1 |
| 9 | `ClearAllActions` | `void` | — |
| 10 | `SetFacing` | `void` | float fDirection |
| 11 | `SwitchPlayerCharacter` | `int` | int nNPC |
| 12 | `SetTime` | `void` | int nHour, int nMinute, int nSecond, int nMillisecond |
| 13 | `SetPartyLeader` | `int` | int nNPC |
| 14 | `SetAreaUnescapable` | `void` | int bUnescapable |
| 15 | `GetAreaUnescapable` | `int` | — |
| 16 | `GetTimeHour` | `int` | — |
| 17 | `GetTimeMinute` | `int` | — |
| 18 | `GetTimeSecond` | `int` | — |
| 19 | `GetTimeMillisecond` | `int` | — |
| 20 | `ActionRandomWalk` | `void` | — |
| 21 | `ActionMoveToLocation` | `void` | location lDestination, int bRun=FALSE |
| 22 | `ActionMoveToObject` | `void` | object oMoveTo, int bRun=FALSE, float fRange=1.0f |
| 23 | `ActionMoveAwayFromObject` | `void` | object oFleeFrom, int bRun=FALSE, float fMoveAwayRange=40.0f |
| 24 | `GetArea` | `object` | object oTarget |
| 25 | `GetEnteringObject` | `object` | — |
| 26 | `GetExitingObject` | `object` | — |
| 27 | `GetPosition` | `vector` | object oTarget |
| 28 | `GetFacing` | `float` | object oTarget |
| 29 | `GetItemPossessor` | `object` | object oItem |
| 30 | `GetItemPossessedBy` | `object` | object oCreature, string sItemTag |
| 31 | `CreateItemOnObject` | `object` | string sItemTemplate, object oTarget=OBJECT_SELF, int nStackSize=1 |
| 32 | `ActionEquipItem` | `void` | object oItem, int nInventorySlot, int bInstant=FALSE |
| 33 | `ActionUnequipItem` | `void` | object oItem, int bInstant=FALSE |
| 34 | `ActionPickUpItem` | `void` | object oItem |
| 35 | `ActionPutDownItem` | `void` | object oItem |
| 36 | `GetLastAttacker` | `object` | object oAttackee=OBJECT_SELF |
| 37 | `ActionAttack` | `void` | object oAttackee, int bPassive=FALSE |
| 38 | `GetNearestCreature` | `object` | int nFirstCriteriaType, int nFirstCriteriaValue, object oTarget=OBJECT_SELF, int nNth=1, int nSecondCriteriaType=-1, int nSecondCriteriaValue=-1, int nThirdCriteriaType=-1, int nThirdCriteriaValue=-1 |
| 39 | `ActionSpeakString` | `void` | string sStringToSpeak, int nTalkVolume=TALKVOLUME_TALK |
| 40 | `ActionPlayAnimation` | `void` | int nAnimation, float fSpeed=1.0, float fDurationSeconds=0.0 |
| 41 | `GetDistanceToObject` | `float` | object oObject |
| 42 | `GetIsObjectValid` | `int` | object oObject |
| 43 | `ActionOpenDoor` | `void` | object oDoor |
| 44 | `ActionCloseDoor` | `void` | object oDoor |
| 45 | `SetCameraFacing` | `void` | float fDirection |
| 46 | `PlaySound` | `void` | string sSoundName |
| 47 | `GetSpellTargetObject` | `object` | — |
| 48 | `ActionCastSpellAtObject` | `void` | int nSpell, object oTarget, int nMetaMagic=0, int bCheat=FALSE, int nDomainLevel=0, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT, int bInstantSpell=FALSE |
| 49 | `GetCurrentHitPoints` | `int` | object oObject=OBJECT_SELF |
| 50 | `GetMaxHitPoints` | `int` | object oObject=OBJECT_SELF |
| 51 | `EffectAssuredHit` | `effect` | — |
| 52 | `GetLastItemEquipped` | `object` | — |
| 53 | `GetSubScreenID` | `int` | — |
| 54 | `CancelCombat` | `void` | object oidCreature |
| 55 | `GetCurrentForcePoints` | `int` | object oObject=OBJECT_SELF |
| 56 | `GetMaxForcePoints` | `int` | object oObject=OBJECT_SELF |
| 57 | `PauseGame` | `void` | int bPause |
| 58 | `SetPlayerRestrictMode` | `void` | int bRestrict |
| 59 | `GetStringLength` | `int` | string sString |
| 60 | `GetStringUpperCase` | `string` | string sString |
| 61 | `GetStringLowerCase` | `string` | string sString |
| 62 | `GetStringRight` | `string` | string sString, int nCount |
| 63 | `GetStringLeft` | `string` | string sString, int nCount |
| 64 | `InsertString` | `string` | string sDestination, string sString, int nPosition |
| 65 | `GetSubString` | `string` | string sString, int nStart, int nCount |
| 66 | `FindSubString` | `int` | string sString, string sSubString |
| 67 | `fabs` | `float` | float fValue |
| 68 | `cos` | `float` | float fValue |
| 69 | `sin` | `float` | float fValue |
| 70 | `tan` | `float` | float fValue |
| 71 | `acos` | `float` | float fValue |
| 72 | `asin` | `float` | float fValue |
| 73 | `atan` | `float` | float fValue |
| 74 | `log` | `float` | float fValue |
| 75 | `pow` | `float` | float fValue, float fExponent |
| 76 | `sqrt` | `float` | float fValue |
| 77 | `abs` | `int` | int nValue |
| 78 | `EffectHeal` | `effect` | int nDamageToHeal |
| 79 | `EffectDamage` | `effect` | int nDamageAmount, int nDamageType=DAMAGE_TYPE_UNIVERSAL, int nDamagePower=DAMAGE_POWER_NORMAL |
| 80 | `EffectAbilityIncrease` | `effect` | int nAbilityToIncrease, int nModifyBy |
| 81 | `EffectDamageResistance` | `effect` | int nDamageType, int nAmount, int nLimit=0 |
| 82 | `EffectResurrection` | `effect` | — |
| 83 | `GetPlayerRestrictMode` | `int` | object oObject=OBJECT_SELF |
| 84 | `GetCasterLevel` | `int` | object oCreature |
| 85 | `GetFirstEffect` | `effect` | object oCreature |
| 86 | `GetNextEffect` | `effect` | object oCreature |
| 87 | `RemoveEffect` | `void` | object oCreature, effect eEffect |
| 88 | `GetIsEffectValid` | `int` | effect eEffect |
| 89 | `GetEffectDurationType` | `int` | effect eEffect |
| 90 | `GetEffectSubType` | `int` | effect eEffect |
| 91 | `GetEffectCreator` | `object` | effect eEffect |
| 92 | `IntToString` | `string` | int nInteger |
| 93 | `GetFirstObjectInArea` | `object` | object oArea=OBJECT_INVALID, int nObjectFilter=OBJECT_TYPE_CREATURE |
| 94 | `GetNextObjectInArea` | `object` | object oArea=OBJECT_INVALID, int nObjectFilter=OBJECT_TYPE_CREATURE |
| 95 | `d2` | `int` | int nNumDice=1 |
| 96 | `d3` | `int` | int nNumDice=1 |
| 97 | `d4` | `int` | int nNumDice=1 |
| 98 | `d6` | `int` | int nNumDice=1 |
| 99 | `d8` | `int` | int nNumDice=1 |
| 100 | `d10` | `int` | int nNumDice=1 |
| 101 | `d12` | `int` | int nNumDice=1 |
| 102 | `d20` | `int` | int nNumDice=1 |
| 103 | `d100` | `int` | int nNumDice=1 |
| 104 | `VectorMagnitude` | `float` | vector vVector |
| 105 | `GetMetaMagicFeat` | `int` | — |
| 106 | `GetObjectType` | `int` | object oTarget |
| 107 | `GetRacialType` | `int` | object oCreature |
| 108 | `FortitudeSave` | `int` | object oCreature, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 109 | `ReflexSave` | `int` | object oCreature, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 110 | `WillSave` | `int` | object oCreature, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 111 | `GetSpellSaveDC` | `int` | — |
| 112 | `MagicalEffect` | `effect` | effect eEffect |
| 113 | `SupernaturalEffect` | `effect` | effect eEffect |
| 114 | `ExtraordinaryEffect` | `effect` | effect eEffect |
| 115 | `EffectACIncrease` | `effect` | int nValue, int nModifyType=AC_DODGE_BONUS, int nDamageType=AC_VS_DAMAGE_TYPE_ALL |
| 116 | `GetAC` | `int` | object oObject, int nForFutureUse=0 |
| 117 | `EffectSavingThrowIncrease` | `effect` | int nSave, int nValue, int nSaveType=SAVING_THROW_TYPE_ALL |
| 118 | `EffectAttackIncrease` | `effect` | int nBonus, int nModifierType=ATTACK_BONUS_MISC |
| 119 | `EffectDamageReduction` | `effect` | int nAmount, int nDamagePower, int nLimit=0 |
| 120 | `EffectDamageIncrease` | `effect` | int nBonus, int nDamageType=DAMAGE_TYPE_UNIVERSAL |
| 121 | `RoundsToSeconds` | `float` | int nRounds |
| 122 | `HoursToSeconds` | `float` | int nHours |
| 123 | `TurnsToSeconds` | `float` | int nTurns |
| 124 | `SoundObjectSetFixedVariance` | `void` | object oSound, float fFixedVariance |
| 125 | `GetGoodEvilValue` | `int` | object oCreature |
| 126 | `GetPartyMemberCount` | `int` | — |
| 127 | `GetAlignmentGoodEvil` | `int` | object oCreature |
| 128 | `GetFirstObjectInShape` | `object` | int nShape, float fSize, location lTarget, int bLineOfSight=FALSE, int nObjectFilter=OBJECT_TYPE_CREATURE, vector vOrigin=[0.0,0.0,0.0] |
| 129 | `GetNextObjectInShape` | `object` | int nShape, float fSize, location lTarget, int bLineOfSight=FALSE, int nObjectFilter=OBJECT_TYPE_CREATURE, vector vOrigin=[0.0,0.0,0.0] |
| 130 | `EffectEntangle` | `effect` | — |
| 131 | `SignalEvent` | `void` | object oObject, event evToRun |
| 132 | `EventUserDefined` | `event` | int nUserDefinedEventNumber |
| 133 | `EffectDeath` | `effect` | int nSpectacularDeath=FALSE, int nDisplayFeedback=TRUE |
| 134 | `EffectKnockdown` | `effect` | — |
| 135 | `ActionGiveItem` | `void` | object oItem, object oGiveTo |
| 136 | `ActionTakeItem` | `void` | object oItem, object oTakeFrom |
| 137 | `VectorNormalize` | `vector` | vector vVector |
| 138 | `GetItemStackSize` | `int` | object oItem |
| 139 | `GetAbilityScore` | `int` | object oCreature, int nAbilityType |
| 140 | `GetIsDead` | `int` | object oCreature |
| 141 | `PrintVector` | `void` | vector vVector, int bPrepend |
| 142 | `Vector` | `vector` | float x=0.0f, float y=0.0f, float z=0.0f |
| 143 | `SetFacingPoint` | `void` | vector vTarget |
| 144 | `AngleToVector` | `vector` | float fAngle |
| 145 | `VectorToAngle` | `float` | vector vVector |
| 146 | `TouchAttackMelee` | `int` | object oTarget, int bDisplayFeedback=TRUE |
| 147 | `TouchAttackRanged` | `int` | object oTarget, int bDisplayFeedback=TRUE |
| 148 | `EffectParalyze` | `effect` | — |
| 149 | `EffectSpellImmunity` | `effect` | int nImmunityToSpell=FORCE_POWER_ALL_FORCE_POWERS |
| 150 | `SetItemStackSize` | `void` | object oItem, int nStackSize |
| 151 | `GetDistanceBetween` | `float` | object oObjectA, object oObjectB |
| 152 | `SetReturnStrref` | `void` | int bShow, int srStringRef=0, int srReturnQueryStrRef=0 |
| 153 | `EffectForceJump` | `effect` | object oTarget, int nAdvanced=0 |
| 154 | `EffectSleep` | `effect` | — |
| 155 | `GetItemInSlot` | `object` | int nInventorySlot, object oCreature=OBJECT_SELF |
| 156 | `EffectTemporaryForcePoints` | `effect` | int nTempForce |
| 157 | `EffectConfused` | `effect` | — |
| 158 | `EffectFrightened` | `effect` | — |
| 159 | `EffectChoke` | `effect` | — |
| 160 | `SetGlobalString` | `void` | string sIdentifier, string sValue |
| 161 | `EffectStunned` | `effect` | — |
| 162 | `SetCommandable` | `void` | int bCommandable, object oTarget=OBJECT_SELF |
| 163 | `GetCommandable` | `int` | object oTarget=OBJECT_SELF |
| 164 | `EffectRegenerate` | `effect` | int nAmount, float fIntervalSeconds |
| 165 | `EffectMovementSpeedIncrease` | `effect` | int nNewSpeedPercent |
| 166 | `GetHitDice` | `int` | object oCreature |
| 167 | `ActionForceFollowObject` | `void` | object oFollow, float fFollowDistance=0.0f |
| 168 | `GetTag` | `string` | object oObject |
| 169 | `ResistForce` | `int` | object oSource, object oTarget |
| 170 | `GetEffectType` | `int` | effect eEffect |
| 171 | `EffectAreaOfEffect` | `effect` | int nAreaEffectId, string sOnEnterScript="", string sHeartbeatScript="", string sOnExitScript="" |
| 172 | `GetFactionEqual` | `int` | object oFirstObject, object oSecondObject=OBJECT_SELF |
| 173 | `ChangeFaction` | `void` | object oObjectToChangeFaction, object oMemberOfFactionToJoin |
| 174 | `GetIsListening` | `int` | object oObject |
| 175 | `SetListening` | `void` | object oObject, int bValue |
| 176 | `SetListenPattern` | `void` | object oObject, string sPattern, int nNumber=0 |
| 177 | `TestStringAgainstPattern` | `int` | string sPattern, string sStringToTest |
| 178 | `GetMatchedSubstring` | `string` | int nString |
| 179 | `GetMatchedSubstringsCount` | `int` | — |
| 180 | `EffectVisualEffect` | `effect` | int nVisualEffectId, int nMissEffect=FALSE |
| 181 | `GetFactionWeakestMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 182 | `GetFactionStrongestMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 183 | `GetFactionMostDamagedMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 184 | `GetFactionLeastDamagedMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 185 | `GetFactionGold` | `int` | object oFactionMember |
| 186 | `GetFactionAverageReputation` | `int` | object oSourceFactionMember, object oTarget |
| 187 | `GetFactionAverageGoodEvilAlignment` | `int` | object oFactionMember |
| 188 | `SoundObjectGetFixedVariance` | `float` | object oSound |
| 189 | `GetFactionAverageLevel` | `int` | object oFactionMember |
| 190 | `GetFactionAverageXP` | `int` | object oFactionMember |
| 191 | `GetFactionMostFrequentClass` | `int` | object oFactionMember |
| 192 | `GetFactionWorstAC` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 193 | `GetFactionBestAC` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 194 | `GetGlobalString` | `string` | string sIdentifier |
| 195 | `GetListenPatternNumber` | `int` | — |
| 196 | `ActionJumpToObject` | `void` | object oToJumpTo, int bWalkStraightLineToPoint=TRUE |
| 197 | `GetWaypointByTag` | `object` | string sWaypointTag |
| 198 | `GetTransitionTarget` | `object` | object oTransition |
| 199 | `EffectLinkEffects` | `effect` | effect eChildEffect, effect eParentEffect |
| 200 | `GetObjectByTag` | `object` | string sTag, int nNth=0 |
| 201 | `AdjustAlignment` | `void` | object oSubject, int nAlignment, int nShift |
| 202 | `ActionWait` | `void` | float fSeconds |
| 203 | `SetAreaTransitionBMP` | `void` | int nPredefinedAreaTransition, string sCustomAreaTransitionBMP="" |
| 204 | `ActionStartConversation` | `void` | object oObjectToConverse, string sDialogResRef="", int bPrivateConversation=FALSE, int nConversationType=CONVERSATION_TYPE_CINEMATIC, int bIgnoreStartRange=FALSE, string sNameObjectToIgnore1="", string sNameObjectToIgnore2="", string sNameObjectToIgnore3="", string sNameObjectToIgnore4="", string sNameObjectToIgnore5="", string sNameObjectToIgnore6="", int bUseLeader=FALSE |
| 205 | `ActionPauseConversation` | `void` | — |
| 206 | `ActionResumeConversation` | `void` | — |
| 207 | `EffectBeam` | `effect` | int nBeamVisualEffect, object oEffector, int nBodyPart, int bMissEffect=FALSE |
| 208 | `GetReputation` | `int` | object oSource, object oTarget |
| 209 | `AdjustReputation` | `void` | object oTarget, object oSourceFactionMember, int nAdjustment |
| 210 | `GetModuleFileName` | `string` | — |
| 211 | `GetGoingToBeAttackedBy` | `object` | object oTarget |
| 212 | `EffectForceResistanceIncrease` | `effect` | int nValue |
| 213 | `GetLocation` | `location` | object oObject |
| 214 | `ActionJumpToLocation` | `void` | location lLocation |
| 215 | `Location` | `location` | vector vPosition, float fOrientation |
| 216 | `ApplyEffectAtLocation` | `void` | int nDurationType, effect eEffect, location lLocation, float fDuration=0.0f |
| 217 | `GetIsPC` | `int` | object oCreature |
| 218 | `FeetToMeters` | `float` | float fFeet |
| 219 | `YardsToMeters` | `float` | float fYards |
| 220 | `ApplyEffectToObject` | `void` | int nDurationType, effect eEffect, object oTarget, float fDuration=0.0f |
| 221 | `SpeakString` | `void` | string sStringToSpeak, int nTalkVolume=TALKVOLUME_TALK |
| 222 | `GetSpellTargetLocation` | `location` | — |
| 223 | `GetPositionFromLocation` | `vector` | location lLocation |
| 224 | `EffectBodyFuel` | `effect` | — |
| 225 | `GetFacingFromLocation` | `float` | location lLocation |
| 226 | `GetNearestCreatureToLocation` | `object` | int nFirstCriteriaType, int nFirstCriteriaValue, location lLocation, int nNth=1, int nSecondCriteriaType=-1, int nSecondCriteriaValue=-1, int nThirdCriteriaType=-1, int nThirdCriteriaValue=-1 |
| 227 | `GetNearestObject` | `object` | int nObjectType=OBJECT_TYPE_ALL, object oTarget=OBJECT_SELF, int nNth=1 |
| 228 | `GetNearestObjectToLocation` | `object` | int nObjectType, location lLocation, int nNth=1 |
| 229 | `GetNearestObjectByTag` | `object` | string sTag, object oTarget=OBJECT_SELF, int nNth=1 |
| 230 | `IntToFloat` | `float` | int nInteger |
| 231 | `FloatToInt` | `int` | float fFloat |
| 232 | `StringToInt` | `int` | string sNumber |
| 233 | `StringToFloat` | `float` | string sNumber |
| 234 | `ActionCastSpellAtLocation` | `void` | int nSpell, location lTargetLocation, int nMetaMagic=0, int bCheat=FALSE, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT, int bInstantSpell=FALSE |
| 235 | `GetIsEnemy` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 236 | `GetIsFriend` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 237 | `GetIsNeutral` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 238 | `GetPCSpeaker` | `object` | — |
| 239 | `GetStringByStrRef` | `string` | int nStrRef |
| 240 | `ActionSpeakStringByStrRef` | `void` | int nStrRef, int nTalkVolume=TALKVOLUME_TALK |
| 241 | `DestroyObject` | `void` | object oDestroy, float fDelay=0.0f, int bNoFade=FALSE, float fDelayUntilFade=0.0f |
| 242 | `GetModule` | `object` | — |
| 243 | `CreateObject` | `object` | int nObjectType, string sTemplate, location lLocation, int bUseAppearAnimation=FALSE |
| 244 | `EventSpellCastAt` | `event` | object oCaster, int nSpell, int bHarmful=TRUE |
| 245 | `GetLastSpellCaster` | `object` | — |
| 246 | `GetLastSpell` | `int` | — |
| 247 | `GetUserDefinedEventNumber` | `int` | — |
| 248 | `GetSpellId` | `int` | — |
| 249 | `RandomName` | `string` | — |
| 250 | `EffectPoison` | `effect` | int nPoisonType |
| 251 | `GetLoadFromSaveGame` | `int` | — |
| 252 | `EffectAssuredDeflection` | `effect` | int nReturn=0 |
| 253 | `GetName` | `string` | object oObject |
| 254 | `GetLastSpeaker` | `object` | — |
| 255 | `BeginConversation` | `int` | string sResRef="", object oObjectToDialog=OBJECT_INVALID |
| 256 | `GetLastPerceived` | `object` | — |
| 257 | `GetLastPerceptionHeard` | `int` | — |
| 258 | `GetLastPerceptionInaudible` | `int` | — |
| 259 | `GetLastPerceptionSeen` | `int` | — |
| 260 | `GetLastClosedBy` | `object` | — |
| 261 | `GetLastPerceptionVanished` | `int` | — |
| 262 | `GetFirstInPersistentObject` | `object` | object oPersistentObject=OBJECT_SELF, int nResidentObjectType=OBJECT_TYPE_CREATURE, int nPersistentZone=PERSISTENT_ZONE_ACTIVE |
| 263 | `GetNextInPersistentObject` | `object` | object oPersistentObject=OBJECT_SELF, int nResidentObjectType=OBJECT_TYPE_CREATURE, int nPersistentZone=PERSISTENT_ZONE_ACTIVE |
| 264 | `GetAreaOfEffectCreator` | `object` | object oAreaOfEffectObject=OBJECT_SELF |
| 265 | `ShowLevelUpGUI` | `int` | — |
| 266 | `SetItemNonEquippable` | `void` | object oItem, int bNonEquippable |
| 267 | `GetButtonMashCheck` | `int` | — |
| 268 | `SetButtonMashCheck` | `void` | int nCheck |
| 269 | `EffectForcePushTargeted` | `effect` | location lCentre, int nIgnoreTestDirectLine=0 |
| 270 | `EffectHaste` | `effect` | — |
| 271 | `GiveItem` | `void` | object oItem, object oGiveTo |
| 272 | `ObjectToString` | `string` | object oObject |
| 273 | `EffectImmunity` | `effect` | int nImmunityType |
| 274 | `GetIsImmune` | `int` | object oCreature, int nImmunityType, object oVersus=OBJECT_INVALID |
| 275 | `EffectDamageImmunityIncrease` | `effect` | int nDamageType, int nPercentImmunity |
| 276 | `GetEncounterActive` | `int` | object oEncounter=OBJECT_SELF |
| 277 | `SetEncounterActive` | `void` | int nNewValue, object oEncounter=OBJECT_SELF |
| 278 | `GetEncounterSpawnsMax` | `int` | object oEncounter=OBJECT_SELF |
| 279 | `SetEncounterSpawnsMax` | `void` | int nNewValue, object oEncounter=OBJECT_SELF |
| 280 | `GetEncounterSpawnsCurrent` | `int` | object oEncounter=OBJECT_SELF |
| 281 | `SetEncounterSpawnsCurrent` | `void` | int nNewValue, object oEncounter=OBJECT_SELF |
| 282 | `GetModuleItemAcquired` | `object` | — |
| 283 | `GetModuleItemAcquiredFrom` | `object` | — |
| 284 | `SetCustomToken` | `void` | int nCustomTokenNumber, string sTokenValue |
| 285 | `GetHasFeat` | `int` | int nFeat, object oCreature=OBJECT_SELF |
| 286 | `GetHasSkill` | `int` | int nSkill, object oCreature=OBJECT_SELF |
| 287 | `ActionUseFeat` | `void` | int nFeat, object oTarget |
| 288 | `ActionUseSkill` | `void` | int nSkill, object oTarget, int nSubSkill=0, object oItemUsed=OBJECT_INVALID |
| 289 | `GetObjectSeen` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 290 | `GetObjectHeard` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 291 | `GetLastPlayerDied` | `object` | — |
| 292 | `GetModuleItemLost` | `object` | — |
| 293 | `GetModuleItemLostBy` | `object` | — |
| 294 | `ActionDoCommand` | `void` | action aActionToDo |
| 295 | `EventConversation` | `event` | — |
| 296 | `SetEncounterDifficulty` | `void` | int nEncounterDifficulty, object oEncounter=OBJECT_SELF |
| 297 | `GetEncounterDifficulty` | `int` | object oEncounter=OBJECT_SELF |
| 298 | `GetDistanceBetweenLocations` | `float` | location lLocationA, location lLocationB |
| 299 | `GetReflexAdjustedDamage` | `int` | int nDamage, object oTarget, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 300 | `PlayAnimation` | `void` | int nAnimation, float fSpeed=1.0, float fSeconds=0.0 |
| 301 | `TalentSpell` | `talent` | int nSpell |
| 302 | `TalentFeat` | `talent` | int nFeat |
| 303 | `TalentSkill` | `talent` | int nSkill |
| 304 | `GetHasSpellEffect` | `int` | int nSpell, object oObject=OBJECT_SELF |
| 305 | `GetEffectSpellId` | `int` | effect eSpellEffect |
| 306 | `GetCreatureHasTalent` | `int` | talent tTalent, object oCreature=OBJECT_SELF |
| 307 | `GetCreatureTalentRandom` | `talent` | int nCategory, object oCreature=OBJECT_SELF, int nInclusion=0 |
| 308 | `GetCreatureTalentBest` | `talent` | int nCategory, int nCRMax, object oCreature=OBJECT_SELF, int nInclusion=0, int nExcludeType=-1, int nExcludeId=-1 |
| 309 | `ActionUseTalentOnObject` | `void` | talent tChosenTalent, object oTarget |
| 310 | `ActionUseTalentAtLocation` | `void` | talent tChosenTalent, location lTargetLocation |
| 311 | `GetGoldPieceValue` | `int` | object oItem |
| 312 | `GetIsPlayableRacialType` | `int` | object oCreature |
| 313 | `JumpToLocation` | `void` | location lDestination |
| 314 | `EffectTemporaryHitpoints` | `effect` | int nHitPoints |
| 315 | `GetSkillRank` | `int` | int nSkill, object oTarget=OBJECT_SELF |
| 316 | `GetAttackTarget` | `object` | object oCreature=OBJECT_SELF |
| 317 | `GetLastAttackType` | `int` | object oCreature=OBJECT_SELF |
| 318 | `GetLastAttackMode` | `int` | object oCreature=OBJECT_SELF |
| 319 | `GetDistanceBetween2D` | `float` | object oObjectA, object oObjectB |
| 320 | `GetIsInCombat` | `int` | object oCreature=OBJECT_SELF |
| 321 | `GetLastAssociateCommand` | `int` | object oAssociate=OBJECT_SELF |
| 322 | `GiveGoldToCreature` | `void` | object oCreature, int nGP |
| 323 | `SetIsDestroyable` | `void` | int bDestroyable, int bRaiseable=TRUE, int bSelectableWhenDead=FALSE |
| 324 | `SetLocked` | `void` | object oTarget, int bLocked |
| 325 | `GetLocked` | `int` | object oTarget |
| 326 | `GetClickingObject` | `object` | — |
| 327 | `SetAssociateListenPatterns` | `void` | object oTarget=OBJECT_SELF |
| 328 | `GetLastWeaponUsed` | `object` | object oCreature |
| 329 | `ActionInteractObject` | `void` | object oPlaceable |
| 330 | `GetLastUsedBy` | `object` | — |
| 331 | `GetAbilityModifier` | `int` | int nAbility, object oCreature=OBJECT_SELF |
| 332 | `GetIdentified` | `int` | object oItem |
| 333 | `SetIdentified` | `void` | object oItem, int bIdentified |
| 334 | `GetDistanceBetweenLocations2D` | `float` | location lLocationA, location lLocationB |
| 335 | `GetDistanceToObject2D` | `float` | object oObject |
| 336 | `GetBlockingDoor` | `object` | — |
| 337 | `GetIsDoorActionPossible` | `int` | object oTargetDoor, int nDoorAction |
| 338 | `DoDoorAction` | `void` | object oTargetDoor, int nDoorAction |
| 339 | `GetFirstItemInInventory` | `object` | object oTarget=OBJECT_SELF |
| 340 | `GetNextItemInInventory` | `object` | object oTarget=OBJECT_SELF |
| 341 | `GetClassByPosition` | `int` | int nClassPosition, object oCreature=OBJECT_SELF |
| 342 | `GetLevelByPosition` | `int` | int nClassPosition, object oCreature=OBJECT_SELF |
| 343 | `GetLevelByClass` | `int` | int nClassType, object oCreature=OBJECT_SELF |
| 344 | `GetDamageDealtByType` | `int` | int nDamageType |
| 345 | `GetTotalDamageDealt` | `int` | — |
| 346 | `GetLastDamager` | `object` | — |
| 347 | `GetLastDisarmed` | `object` | — |
| 348 | `GetLastDisturbed` | `object` | — |
| 349 | `GetLastLocked` | `object` | — |
| 350 | `GetLastUnlocked` | `object` | — |
| 351 | `EffectSkillIncrease` | `effect` | int nSkill, int nValue |
| 352 | `GetInventoryDisturbType` | `int` | — |
| 353 | `GetInventoryDisturbItem` | `object` | — |
| 354 | `ShowUpgradeScreen` | `void` | object oItem=OBJECT_INVALID |
| 355 | `VersusAlignmentEffect` | `effect` | effect eEffect, int nLawChaos=ALIGNMENT_ALL, int nGoodEvil=ALIGNMENT_ALL |
| 356 | `VersusRacialTypeEffect` | `effect` | effect eEffect, int nRacialType |
| 357 | `VersusTrapEffect` | `effect` | effect eEffect |
| 358 | `GetGender` | `int` | object oCreature |
| 359 | `GetIsTalentValid` | `int` | talent tTalent |
| 360 | `ActionMoveAwayFromLocation` | `void` | location lMoveAwayFrom, int bRun=FALSE, float fMoveAwayRange=40.0f |
| 361 | `GetAttemptedAttackTarget` | `object` | — |
| 362 | `GetTypeFromTalent` | `int` | talent tTalent |
| 363 | `GetIdFromTalent` | `int` | talent tTalent |
| 364 | `PlayPazaak` | `void` | int nOpponentPazaakDeck, string sEndScript, int nMaxWager, int bShowTutorial=FALSE, object oOpponent=OBJECT_INVALID |
| 365 | `GetLastPazaakResult` | `int` | — |
| 366 | `DisplayFeedBackText` | `void` | object oCreature, int nTextConstant |
| 367 | `AddJournalQuestEntry` | `void` | string szPlotID, int nState, int bAllowOverrideHigher=FALSE |
| 368 | `RemoveJournalQuestEntry` | `void` | string szPlotID |
| 369 | `GetJournalEntry` | `int` | string szPlotID |
| 370 | `PlayRumblePattern` | `int` | int nPattern |
| 371 | `StopRumblePattern` | `int` | int nPattern |
| 372 | `EffectDamageForcePoints` | `effect` | int nDamage |
| 373 | `EffectHealForcePoints` | `effect` | int nHeal |
| 374 | `SendMessageToPC` | `void` | object oPlayer, string szMessage |
| 375 | `GetAttemptedSpellTarget` | `object` | — |
| 376 | `GetLastOpenedBy` | `object` | — |
| 377 | `GetHasSpell` | `int` | int nSpell, object oCreature=OBJECT_SELF |
| 378 | `OpenStore` | `void` | object oStore, object oPC, int nBonusMarkUp=0, int nBonusMarkDown=0 |
| 379 | `ActionSurrenderToEnemies` | `void` | — |
| 380 | `GetFirstFactionMember` | `object` | object oMemberOfFaction, int bPCOnly=TRUE |
| 381 | `GetNextFactionMember` | `object` | object oMemberOfFaction, int bPCOnly=TRUE |
| 382 | `ActionForceMoveToLocation` | `void` | location lDestination, int bRun=FALSE, float fTimeout=30.0f |
| 383 | `ActionForceMoveToObject` | `void` | object oMoveTo, int bRun=FALSE, float fRange=1.0f, float fTimeout=30.0f |
| 384 | `GetJournalQuestExperience` | `int` | string szPlotID |
| 385 | `JumpToObject` | `void` | object oToJumpTo, int nWalkStraightLineToPoint=1 |
| 386 | `SetMapPinEnabled` | `void` | object oMapPin, int nEnabled |
| 387 | `EffectHitPointChangeWhenDying` | `effect` | float fHitPointChangePerRound |
| 388 | `PopUpGUIPanel` | `void` | object oPC, int nGUIPanel |
| 389 | `AddMultiClass` | `void` | int nClassType, object oSource |
| 390 | `GetIsLinkImmune` | `int` | object oTarget, effect eEffect |
| 391 | `EffectDroidStun` | `effect` | — |
| 392 | `EffectForcePushed` | `effect` | — |
| 393 | `GiveXPToCreature` | `void` | object oCreature, int nXpAmount |
| 394 | `SetXP` | `void` | object oCreature, int nXpAmount |
| 395 | `GetXP` | `int` | object oCreature |
| 396 | `IntToHexString` | `string` | int nInteger |
| 397 | `GetBaseItemType` | `int` | object oItem |
| 398 | `GetItemHasItemProperty` | `int` | object oItem, int nProperty |
| 399 | `ActionEquipMostDamagingMelee` | `void` | object oVersus=OBJECT_INVALID, int bOffHand=FALSE |
| 400 | `ActionEquipMostDamagingRanged` | `void` | object oVersus=OBJECT_INVALID |
| 401 | `GetItemACValue` | `int` | object oItem |
| 402 | `EffectForceResisted` | `effect` | object oSource |
| 403 | `ExploreAreaForPlayer` | `void` | object oArea, object oPlayer |
| 404 | `ActionEquipMostEffectiveArmor` | `void` | — |
| 405 | `GetIsDay` | `int` | — |
| 406 | `GetIsNight` | `int` | — |
| 407 | `GetIsDawn` | `int` | — |
| 408 | `GetIsDusk` | `int` | — |
| 409 | `GetIsEncounterCreature` | `int` | object oCreature=OBJECT_SELF |
| 410 | `GetLastPlayerDying` | `object` | — |
| 411 | `GetStartingLocation` | `location` | — |
| 412 | `ChangeToStandardFaction` | `void` | object oCreatureToChange, int nStandardFaction |
| 413 | `SoundObjectPlay` | `void` | object oSound |
| 414 | `SoundObjectStop` | `void` | object oSound |
| 415 | `SoundObjectSetVolume` | `void` | object oSound, int nVolume |
| 416 | `SoundObjectSetPosition` | `void` | object oSound, vector vPosition |
| 417 | `SpeakOneLinerConversation` | `void` | string sDialogResRef="", object oTokenTarget=OBJECT_TYPE_INVALID |
| 418 | `GetGold` | `int` | object oTarget=OBJECT_SELF |
| 419 | `GetLastRespawnButtonPresser` | `object` | — |
| 420 | `EffectForceFizzle` | `effect` | — |
| 421 | `SetLightsaberPowered` | `void` | object oCreature, int bOverride, int bPowered=TRUE, int bShowTransition=FALSE |
| 422 | `GetIsWeaponEffective` | `int` | object oVersus=OBJECT_INVALID, int bOffHand=FALSE |
| 423 | `GetLastSpellHarmful` | `int` | — |
| 424 | `EventActivateItem` | `event` | object oItem, location lTarget, object oTarget=OBJECT_INVALID |
| 425 | `MusicBackgroundPlay` | `void` | object oArea |
| 426 | `MusicBackgroundStop` | `void` | object oArea |
| 427 | `MusicBackgroundSetDelay` | `void` | object oArea, int nDelay |
| 428 | `MusicBackgroundChangeDay` | `void` | object oArea, int nTrack |
| 429 | `MusicBackgroundChangeNight` | `void` | object oArea, int nTrack |
| 430 | `MusicBattlePlay` | `void` | object oArea |
| 431 | `MusicBattleStop` | `void` | object oArea |
| 432 | `MusicBattleChange` | `void` | object oArea, int nTrack |
| 433 | `AmbientSoundPlay` | `void` | object oArea |
| 434 | `AmbientSoundStop` | `void` | object oArea |
| 435 | `AmbientSoundChangeDay` | `void` | object oArea, int nTrack |
| 436 | `AmbientSoundChangeNight` | `void` | object oArea, int nTrack |
| 437 | `GetLastKiller` | `object` | — |
| 438 | `GetSpellCastItem` | `object` | — |
| 439 | `GetItemActivated` | `object` | — |
| 440 | `GetItemActivator` | `object` | — |
| 441 | `GetItemActivatedTargetLocation` | `location` | — |
| 442 | `GetItemActivatedTarget` | `object` | — |
| 443 | `GetIsOpen` | `int` | object oObject |
| 444 | `TakeGoldFromCreature` | `void` | int nAmount, object oCreatureToTakeFrom, int bDestroy=FALSE |
| 445 | `GetIsInConversation` | `int` | object oObject |
| 446 | `EffectAbilityDecrease` | `effect` | int nAbility, int nModifyBy |
| 447 | `EffectAttackDecrease` | `effect` | int nPenalty, int nModifierType=ATTACK_BONUS_MISC |
| 448 | `EffectDamageDecrease` | `effect` | int nPenalty, int nDamageType=DAMAGE_TYPE_UNIVERSAL |
| 449 | `EffectDamageImmunityDecrease` | `effect` | int nDamageType, int nPercentImmunity |
| 450 | `EffectACDecrease` | `effect` | int nValue, int nModifyType=AC_DODGE_BONUS, int nDamageType=AC_VS_DAMAGE_TYPE_ALL |
| 451 | `EffectMovementSpeedDecrease` | `effect` | int nPercentChange |
| 452 | `EffectSavingThrowDecrease` | `effect` | int nSave, int nValue, int nSaveType=SAVING_THROW_TYPE_ALL |
| 453 | `EffectSkillDecrease` | `effect` | int nSkill, int nValue |
| 454 | `EffectForceResistanceDecrease` | `effect` | int nValue |
| 455 | `GetPlotFlag` | `int` | object oTarget=OBJECT_SELF |
| 456 | `SetPlotFlag` | `void` | object oTarget, int nPlotFlag |
| 457 | `EffectInvisibility` | `effect` | int nInvisibilityType |
| 458 | `EffectConcealment` | `effect` | int nPercentage |
| 459 | `EffectForceShield` | `effect` | int nShield |
| 460 | `EffectDispelMagicAll` | `effect` | int nCasterLevel |
| 461 | `SetDialogPlaceableCamera` | `void` | int nCameraId |
| 462 | `GetSoloMode` | `int` | — |
| 463 | `EffectDisguise` | `effect` | int nDisguiseAppearance |
| 464 | `GetMaxStealthXP` | `int` | — |
| 465 | `EffectTrueSeeing` | `effect` | — |
| 466 | `EffectSeeInvisible` | `effect` | — |
| 467 | `EffectTimeStop` | `effect` | — |
| 468 | `SetMaxStealthXP` | `void` | int nMax |
| 469 | `EffectBlasterDeflectionIncrease` | `effect` | int nChange |
| 470 | `EffectBlasterDeflectionDecrease` | `effect` | int nChange |
| 471 | `EffectHorrified` | `effect` | — |
| 472 | `EffectSpellLevelAbsorption` | `effect` | int nMaxSpellLevelAbsorbed, int nTotalSpellLevelsAbsorbed=0, int nSpellSchool=0 |
| 473 | `EffectDispelMagicBest` | `effect` | int nCasterLevel |
| 474 | `GetCurrentStealthXP` | `int` | — |
| 475 | `GetNumStackedItems` | `int` | object oItem |
| 476 | `SurrenderToEnemies` | `void` | — |
| 477 | `EffectMissChance` | `effect` | int nPercentage |
| 478 | `SetCurrentStealthXP` | `void` | int nCurrent |
| 479 | `GetCreatureSize` | `int` | object oCreature |
| 480 | `AwardStealthXP` | `void` | object oTarget |
| 481 | `GetStealthXPEnabled` | `int` | — |
| 482 | `SetStealthXPEnabled` | `void` | int bEnabled |
| 483 | `ActionUnlockObject` | `void` | object oTarget |
| 484 | `ActionLockObject` | `void` | object oTarget |
| 485 | `EffectModifyAttacks` | `effect` | int nAttacks |
| 486 | `GetLastTrapDetected` | `object` | object oTarget=OBJECT_SELF |
| 487 | `EffectDamageShield` | `effect` | int nDamageAmount, int nRandomAmount, int nDamageType |
| 488 | `GetNearestTrapToObject` | `object` | object oTarget=OBJECT_SELF, int nTrapDetected=TRUE |
| 489 | `GetAttemptedMovementTarget` | `object` | — |
| 490 | `GetBlockingCreature` | `object` | object oTarget=OBJECT_SELF |
| 491 | `GetFortitudeSavingThrow` | `int` | object oTarget |
| 492 | `GetWillSavingThrow` | `int` | object oTarget |
| 493 | `GetReflexSavingThrow` | `int` | object oTarget |
| 494 | `GetChallengeRating` | `float` | object oCreature |
| 495 | `GetFoundEnemyCreature` | `object` | object oTarget=OBJECT_SELF |
| 496 | `GetMovementRate` | `int` | object oCreature |
| 497 | `GetSubRace` | `int` | object oCreature |
| 498 | `GetStealthXPDecrement` | `int` | — |
| 499 | `SetStealthXPDecrement` | `void` | int nDecrement |
| 500 | `DuplicateHeadAppearance` | `void` | object oidCreatureToChange, object oidCreatureToMatch |
| 501 | `ActionCastFakeSpellAtObject` | `void` | int nSpell, object oTarget, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT |
| 502 | `ActionCastFakeSpellAtLocation` | `void` | int nSpell, location lTarget, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT |
| 503 | `CutsceneAttack` | `void` | object oTarget, int nAnimation, int nAttackResult, int nDamage |
| 504 | `SetCameraMode` | `void` | object oPlayer, int nCameraMode |
| 505 | `SetLockOrientationInDialog` | `void` | object oObject, int nValue |
| 506 | `SetLockHeadFollowInDialog` | `void` | object oObject, int nValue |
| 507 | `CutsceneMove` | `void` | object oObject, vector vPosition, int nRun |
| 508 | `EnableVideoEffect` | `void` | int nEffectType |
| 509 | `StartNewModule` | `void` | string sModuleName, string sWayPoint="", string sMovie1="", string sMovie2="", string sMovie3="", string sMovie4="", string sMovie5="", string sMovie6="" |
| 510 | `DisableVideoEffect` | `void` | — |
| 511 | `GetWeaponRanged` | `int` | object oItem |
| 512 | `DoSinglePlayerAutoSave` | `void` | — |
| 513 | `GetGameDifficulty` | `int` | — |
| 514 | `GetUserActionsPending` | `int` | — |
| 515 | `RevealMap` | `void` | vector vPoint=[0.0,0.0,0.0], int nRadius=-1 |
| 516 | `SetTutorialWindowsEnabled` | `void` | int bEnabled |
| 517 | `ShowTutorialWindow` | `void` | int nWindow |
| 518 | `StartCreditSequence` | `void` | int bTransparentBackground |
| 519 | `IsCreditSequenceInProgress` | `int` | — |
| 520 | `SWMG_SetLateralAccelerationPerSecond` | `void` | float fLAPS |
| 521 | `SWMG_GetLateralAccelerationPerSecond` | `float` | — |
| 522 | `GetCurrentAction` | `int` | object oObject=OBJECT_SELF |
| 523 | `GetDifficultyModifier` | `float` | — |
| 524 | `GetAppearanceType` | `int` | object oCreature |
| 525 | `FloatingTextStrRefOnCreature` | `void` | int nStrRefToDisplay, object oCreatureToFloatAbove, int bBroadcastToFaction=TRUE |
| 526 | `FloatingTextStringOnCreature` | `void` | string sStringToDisplay, object oCreatureToFloatAbove, int bBroadcastToFaction=TRUE |
| 527 | `GetTrapDisarmable` | `int` | object oTrapObject |
| 528 | `GetTrapDetectable` | `int` | object oTrapObject |
| 529 | `GetTrapDetectedBy` | `int` | object oTrapObject, object oCreature |
| 530 | `GetTrapFlagged` | `int` | object oTrapObject |
| 531 | `GetTrapBaseType` | `int` | object oTrapObject |
| 532 | `GetTrapOneShot` | `int` | object oTrapObject |
| 533 | `GetTrapCreator` | `object` | object oTrapObject |
| 534 | `GetTrapKeyTag` | `string` | object oTrapObject |
| 535 | `GetTrapDisarmDC` | `int` | object oTrapObject |
| 536 | `GetTrapDetectDC` | `int` | object oTrapObject |
| 537 | `GetLockKeyRequired` | `int` | object oObject |
| 538 | `GetLockKeyTag` | `int` | object oObject |
| 539 | `GetLockLockable` | `int` | object oObject |
| 540 | `GetLockUnlockDC` | `int` | object oObject |
| 541 | `GetLockLockDC` | `int` | object oObject |
| 542 | `GetPCLevellingUp` | `object` | — |
| 543 | `GetHasFeatEffect` | `int` | int nFeat, object oObject=OBJECT_SELF |
| 544 | `SetPlaceableIllumination` | `void` | object oPlaceable=OBJECT_SELF, int bIlluminate=TRUE |
| 545 | `GetPlaceableIllumination` | `int` | object oPlaceable=OBJECT_SELF |
| 546 | `GetIsPlaceableObjectActionPossible` | `int` | object oPlaceable, int nPlaceableAction |
| 547 | `DoPlaceableObjectAction` | `void` | object oPlaceable, int nPlaceableAction |
| 548 | `GetFirstPC` | `object` | — |
| 549 | `GetNextPC` | `object` | — |
| 550 | `SetTrapDetectedBy` | `int` | object oTrap, object oDetector |
| 551 | `GetIsTrapped` | `int` | object oObject |
| 552 | `SetEffectIcon` | `effect` | effect eEffect, int nIcon |
| 553 | `FaceObjectAwayFromObject` | `void` | object oFacer, object oObjectToFaceAwayFrom |
| 554 | `PopUpDeathGUIPanel` | `void` | object oPC, int bRespawnButtonEnabled=TRUE, int bWaitForHelpButtonEnabled=TRUE, int nHelpStringReference=0, string sHelpString="" |
| 555 | `SetTrapDisabled` | `void` | object oTrap |
| 556 | `GetLastHostileActor` | `object` | object oVictim=OBJECT_SELF |
| 557 | `ExportAllCharacters` | `void` | — |
| 558 | `MusicBackgroundGetDayTrack` | `int` | object oArea |
| 559 | `MusicBackgroundGetNightTrack` | `int` | object oArea |
| 560 | `WriteTimestampedLogEntry` | `void` | string sLogEntry |
| 561 | `GetModuleName` | `string` | — |
| 562 | `GetFactionLeader` | `object` | object oMemberOfFaction |
| 563 | `SWMG_SetSpeedBlurEffect` | `void` | int bEnabled, float fRatio=0.75f |
| 564 | `EndGame` | `void` | int nShowEndGameGui=TRUE |
| 565 | `GetRunScriptVar` | `int` | — |
| 566 | `GetCreatureMovmentType` | `int` | object oidCreature |
| 567 | `AmbientSoundSetDayVolume` | `void` | object oArea, int nVolume |
| 568 | `AmbientSoundSetNightVolume` | `void` | object oArea, int nVolume |
| 569 | `MusicBackgroundGetBattleTrack` | `int` | object oArea |
| 570 | `GetHasInventory` | `int` | object oObject |
| 571 | `GetStrRefSoundDuration` | `float` | int nStrRef |
| 572 | `AddToParty` | `void` | object oPC, object oPartyLeader |
| 573 | `RemoveFromParty` | `void` | object oPC |
| 574 | `AddPartyMember` | `int` | int nNPC, object oCreature |
| 575 | `RemovePartyMember` | `int` | int nNPC |
| 576 | `IsObjectPartyMember` | `int` | object oCreature |
| 577 | `GetPartyMemberByIndex` | `object` | int nIndex |
| 578 | `GetGlobalBoolean` | `int` | string sIdentifier |
| 579 | `SetGlobalBoolean` | `void` | string sIdentifier, int nValue |
| 580 | `GetGlobalNumber` | `int` | string sIdentifier |
| 581 | `SetGlobalNumber` | `void` | string sIdentifier, int nValue |
| 582 | `AurPostString` | `void` | string sString, int nX, int nY, float fLife |
| 583 | `SWMG_GetLastEvent` | `string` | — |
| 584 | `SWMG_GetLastEventModelName` | `string` | — |
| 585 | `SWMG_GetObjectByName` | `object` | string sName |
| 586 | `SWMG_PlayAnimation` | `void` | object oObject, string sAnimName, int bLooping=1, int bQueue=0, int bOverlay=0 |
| 587 | `SWMG_GetLastBulletHitDamage` | `int` | — |
| 588 | `SWMG_GetLastBulletHitTarget` | `int` | — |
| 589 | `SWMG_GetLastBulletHitShooter` | `object` | — |
| 590 | `SWMG_AdjustFollowerHitPoints` | `int` | object oFollower, int nHP, int nAbsolute=0 |
| 591 | `SWMG_OnBulletHit` | `void` | — |
| 592 | `SWMG_OnObstacleHit` | `void` | — |
| 593 | `SWMG_GetLastFollowerHit` | `object` | — |
| 594 | `SWMG_GetLastObstacleHit` | `object` | — |
| 595 | `SWMG_GetLastBulletFiredDamage` | `int` | — |
| 596 | `SWMG_GetLastBulletFiredTarget` | `int` | — |
| 597 | `SWMG_GetObjectName` | `string` | object oid=OBJECT_SELF |
| 598 | `SWMG_OnDeath` | `void` | — |
| 599 | `SWMG_IsFollower` | `int` | object oid=OBJECT_SELF |
| 600 | `SWMG_IsPlayer` | `int` | object oid=OBJECT_SELF |
| 601 | `SWMG_IsEnemy` | `int` | object oid=OBJECT_SELF |
| 602 | `SWMG_IsTrigger` | `int` | object oid=OBJECT_SELF |
| 603 | `SWMG_IsObstacle` | `int` | object oid=OBJECT_SELF |
| 604 | `SWMG_SetFollowerHitPoints` | `void` | object oFollower, int nHP |
| 605 | `SWMG_OnDamage` | `void` | — |
| 606 | `SWMG_GetLastHPChange` | `int` | — |
| 607 | `SWMG_RemoveAnimation` | `void` | object oObject, string sAnimName |
| 608 | `SWMG_GetCameraNearClip` | `float` | — |
| 609 | `SWMG_GetCameraFarClip` | `float` | — |
| 610 | `SWMG_SetCameraClip` | `void` | float fNear, float fFar |
| 611 | `SWMG_GetPlayer` | `object` | — |
| 612 | `SWMG_GetEnemyCount` | `int` | — |
| 613 | `SWMG_GetEnemy` | `object` | int nEntry |
| 614 | `SWMG_GetObstacleCount` | `int` | — |
| 615 | `SWMG_GetObstacle` | `object` | int nEntry |
| 616 | `SWMG_GetHitPoints` | `int` | object oFollower |
| 617 | `SWMG_GetMaxHitPoints` | `int` | object oFollower |
| 618 | `SWMG_SetMaxHitPoints` | `void` | object oFollower, int nMaxHP |
| 619 | `SWMG_GetSphereRadius` | `float` | object oFollower |
| 620 | `SWMG_SetSphereRadius` | `void` | object oFollower, float fRadius |
| 621 | `SWMG_GetNumLoops` | `int` | object oFollower |
| 622 | `SWMG_SetNumLoops` | `void` | object oFollower, int nNumLoops |
| 623 | `SWMG_GetPosition` | `vector` | object oFollower |
| 624 | `SWMG_GetGunBankCount` | `int` | object oFollower |
| 625 | `SWMG_GetGunBankBulletModel` | `string` | object oFollower, int nGunBank |
| 626 | `SWMG_GetGunBankGunModel` | `string` | object oFollower, int nGunBank |
| 627 | `SWMG_GetGunBankDamage` | `int` | object oFollower, int nGunBank |
| 628 | `SWMG_GetGunBankTimeBetweenShots` | `float` | object oFollower, int nGunBank |
| 629 | `SWMG_GetGunBankLifespan` | `float` | object oFollower, int nGunBank |
| 630 | `SWMG_GetGunBankSpeed` | `float` | object oFollower, int nGunBank |
| 631 | `SWMG_GetGunBankTarget` | `int` | object oFollower, int nGunBank |
| 632 | `SWMG_SetGunBankBulletModel` | `void` | object oFollower, int nGunBank, string sBulletModel |
| 633 | `SWMG_SetGunBankGunModel` | `void` | object oFollower, int nGunBank, string sGunModel |
| 634 | `SWMG_SetGunBankDamage` | `void` | object oFollower, int nGunBank, int nDamage |
| 635 | `SWMG_SetGunBankTimeBetweenShots` | `void` | object oFollower, int nGunBank, float fTBS |
| 636 | `SWMG_SetGunBankLifespan` | `void` | object oFollower, int nGunBank, float fLifespan |
| 637 | `SWMG_SetGunBankSpeed` | `void` | object oFollower, int nGunBank, float fSpeed |
| 638 | `SWMG_SetGunBankTarget` | `void` | object oFollower, int nGunBank, int nTarget |
| 639 | `SWMG_GetLastBulletHitPart` | `string` | — |
| 640 | `SWMG_IsGunBankTargetting` | `int` | object oFollower, int nGunBank |
| 641 | `SWMG_GetPlayerOffset` | `vector` | — |
| 642 | `SWMG_GetPlayerInvincibility` | `float` | — |
| 643 | `SWMG_GetPlayerSpeed` | `float` | — |
| 644 | `SWMG_GetPlayerMinSpeed` | `float` | — |
| 645 | `SWMG_GetPlayerAccelerationPerSecond` | `float` | — |
| 646 | `SWMG_GetPlayerTunnelPos` | `vector` | — |
| 647 | `SWMG_SetPlayerOffset` | `void` | vector vOffset |
| 648 | `SWMG_SetPlayerInvincibility` | `void` | float fInvincibility |
| 649 | `SWMG_SetPlayerSpeed` | `void` | float fSpeed |
| 650 | `SWMG_SetPlayerMinSpeed` | `void` | float fMinSpeed |
| 651 | `SWMG_SetPlayerAccelerationPerSecond` | `void` | float fAPS |
| 652 | `SWMG_SetPlayerTunnelPos` | `void` | vector vTunnel |
| 653 | `SWMG_GetPlayerTunnelNeg` | `vector` | — |
| 654 | `SWMG_SetPlayerTunnelNeg` | `void` | vector vTunnel |
| 655 | `SWMG_GetPlayerOrigin` | `vector` | — |
| 656 | `SWMG_SetPlayerOrigin` | `void` | vector vOrigin |
| 657 | `SWMG_GetGunBankHorizontalSpread` | `float` | object oEnemy, int nGunBank |
| 658 | `SWMG_GetGunBankVerticalSpread` | `float` | object oEnemy, int nGunBank |
| 659 | `SWMG_GetGunBankSensingRadius` | `float` | object oEnemy, int nGunBank |
| 660 | `SWMG_GetGunBankInaccuracy` | `float` | object oEnemy, int nGunBank |
| 661 | `SWMG_SetGunBankHorizontalSpread` | `void` | object oEnemy, int nGunBank, float fHorizontalSpread |
| 662 | `SWMG_SetGunBankVerticalSpread` | `void` | object oEnemy, int nGunBank, float fVerticalSpread |
| 663 | `SWMG_SetGunBankSensingRadius` | `void` | object oEnemy, int nGunBank, float fSensingRadius |
| 664 | `SWMG_SetGunBankInaccuracy` | `void` | object oEnemy, int nGunBank, float fInaccuracy |
| 665 | `SWMG_GetIsInvulnerable` | `int` | object oFollower |
| 666 | `SWMG_StartInvulnerability` | `void` | object oFollower |
| 667 | `SWMG_GetPlayerMaxSpeed` | `float` | — |
| 668 | `SWMG_SetPlayerMaxSpeed` | `void` | float fMaxSpeed |
| 669 | `AddJournalWorldEntry` | `void` | int nIndex, string szEntry, string szTitle="World Entry" |
| 670 | `AddJournalWorldEntryStrref` | `void` | int strref, int strrefTitle |
| 671 | `BarkString` | `void` | object oCreature, int strRef |
| 672 | `DeleteJournalWorldAllEntries` | `void` | — |
| 673 | `DeleteJournalWorldEntry` | `void` | int nIndex |
| 674 | `DeleteJournalWorldEntryStrref` | `void` | int strref |
| 675 | `EffectForceDrain` | `effect` | int nDamage |
| 676 | `EffectPsychicStatic` | `effect` | — |
| 677 | `PlayVisualAreaEffect` | `void` | int nEffectID, location lTarget |
| 678 | `SetJournalQuestEntryPicture` | `void` | string szPlotID, object oObject, int nPictureIndex, int bAllPartyMemebers=TRUE, int bAllPlayers=FALSE |
| 679 | `GetLocalBoolean` | `int` | object oObject, int nIndex |
| 680 | `SetLocalBoolean` | `void` | object oObject, int nIndex, int nValue |
| 681 | `GetLocalNumber` | `int` | object oObject, int nIndex |
| 682 | `SetLocalNumber` | `void` | object oObject, int nIndex, int nValue |
| 683 | `SWMG_GetSoundFrequency` | `int` | object oFollower, int nSound |
| 684 | `SWMG_SetSoundFrequency` | `void` | object oFollower, int nSound, int nFrequency |
| 685 | `SWMG_GetSoundFrequencyIsRandom` | `int` | object oFollower, int nSound |
| 686 | `SWMG_SetSoundFrequencyIsRandom` | `void` | object oFollower, int nSound, int bIsRandom |
| 687 | `SWMG_GetSoundVolume` | `int` | object oFollower, int nSound |
| 688 | `SWMG_SetSoundVolume` | `void` | object oFollower, int nSound, int nVolume |
| 689 | `SoundObjectGetPitchVariance` | `float` | object oSound |
| 690 | `SoundObjectSetPitchVariance` | `void` | object oSound, float fVariance |
| 691 | `SoundObjectGetVolume` | `int` | object oSound |
| 692 | `GetGlobalLocation` | `location` | string sIdentifier |
| 693 | `SetGlobalLocation` | `void` | string sIdentifier, location lValue |
| 694 | `AddAvailableNPCByObject` | `int` | int nNPC, object oCreature |
| 695 | `RemoveAvailableNPC` | `int` | int nNPC |
| 696 | `IsAvailableCreature` | `int` | int nNPC |
| 697 | `AddAvailableNPCByTemplate` | `int` | int nNPC, string sTemplate |
| 698 | `SpawnAvailableNPC` | `object` | int nNPC, location lPosition |
| 699 | `IsNPCPartyMember` | `int` | int nNPC |
| 700 | `ActionBarkString` | `void` | int strRef |
| 701 | `GetIsConversationActive` | `int` | — |
| 702 | `EffectLightsaberThrow` | `effect` | object oTarget1, object oTarget2=OBJECT_INVALID, object oTarget3=OBJECT_INVALID, int nAdvancedDamage=0 |
| 703 | `EffectWhirlWind` | `effect` | — |
| 704 | `GetPartyAIStyle` | `int` | — |
| 705 | `GetNPCAIStyle` | `int` | object oCreature |
| 706 | `SetPartyAIStyle` | `void` | int nStyle |
| 707 | `SetNPCAIStyle` | `void` | object oCreature, int nStyle |
| 708 | `SetNPCSelectability` | `void` | int nNPC, int nSelectability |
| 709 | `GetNPCSelectability` | `int` | int nNPC |
| 710 | `ClearAllEffects` | `void` | — |
| 711 | `GetLastConversation` | `string` | — |
| 712 | `ShowPartySelectionGUI` | `void` | string sExitScript="", int nForceNPC1=-1, int nForceNPC2=-1 |
| 713 | `GetStandardFaction` | `int` | object oObject |
| 714 | `GivePlotXP` | `void` | string sPlotName, int nPercentage |
| 715 | `GetMinOneHP` | `int` | object oObject |
| 716 | `SetMinOneHP` | `void` | object oObject, int nMinOneHP |
| 717 | `SWMG_GetPlayerTunnelInfinite` | `vector` | — |
| 718 | `SWMG_SetPlayerTunnelInfinite` | `void` | vector vInfinite |
| 719 | `SetGlobalFadeIn` | `void` | float fWait=0.0f, float fLength=0.0f, float fR=0.0f, float fG=0.0f, float fB=0.0f |
| 720 | `SetGlobalFadeOut` | `void` | float fWait=0.0f, float fLength=0.0f, float fR=0.0f, float fG=0.0f, float fB=0.0f |
| 721 | `GetLastHostileTarget` | `object` | object oAttacker=OBJECT_SELF |
| 722 | `GetLastAttackAction` | `int` | object oAttacker=OBJECT_SELF |
| 723 | `GetLastForcePowerUsed` | `int` | object oAttacker=OBJECT_SELF |
| 724 | `GetLastCombatFeatUsed` | `int` | object oAttacker=OBJECT_SELF |
| 725 | `GetLastAttackResult` | `int` | object oAttacker=OBJECT_SELF |
| 726 | `GetWasForcePowerSuccessful` | `int` | object oAttacker=OBJECT_SELF |
| 727 | `GetFirstAttacker` | `object` | object oCreature=OBJECT_SELF |
| 728 | `GetNextAttacker` | `object` | object oCreature=OBJECT_SELF |
| 729 | `SetFormation` | `void` | object oAnchor, object oCreature, int nFormationPattern, int nPosition |
| 730 | `ActionFollowLeader` | `void` | — |
| 731 | `SetForcePowerUnsuccessful` | `void` | int nResult, object oCreature=OBJECT_SELF |
| 732 | `GetIsDebilitated` | `int` | object oCreature=OBJECT_SELF |
| 733 | `PlayMovie` | `void` | string sMovie |
| 734 | `SaveNPCState` | `void` | int nNPC |
| 735 | `GetCategoryFromTalent` | `int` | talent tTalent |
| 736 | `SurrenderByFaction` | `void` | int nFactionFrom, int nFactionTo |
| 737 | `ChangeFactionByFaction` | `void` | int nFactionFrom, int nFactionTo |
| 738 | `PlayRoomAnimation` | `void` | string sRoom, int nAnimation |
| 739 | `ShowGalaxyMap` | `void` | int nPlanet |
| 740 | `SetPlanetSelectable` | `void` | int nPlanet, int bSelectable |
| 741 | `GetPlanetSelectable` | `int` | int nPlanet |
| 742 | `SetPlanetAvailable` | `void` | int nPlanet, int bAvailable |
| 743 | `GetPlanetAvailable` | `int` | int nPlanet |
| 744 | `GetSelectedPlanet` | `int` | — |
| 745 | `SoundObjectFadeAndStop` | `void` | object oSound, float fSeconds |
| 746 | `SetAreaFogColor` | `void` | object oArea, float fRed, float fGreen, float fBlue |
| 747 | `ChangeItemCost` | `void` | string sItem, float fCostMultiplier |
| 748 | `GetIsLiveContentAvailable` | `int` | int nPkg |
| 749 | `ResetDialogState` | `void` | — |
| 750 | `SetGoodEvilValue` | `void` | object oCreature, int nAlignment |
| 751 | `GetIsPoisoned` | `int` | object oObject |
| 752 | `GetSpellTarget` | `object` | object oCreature=OBJECT_SELF |
| 753 | `SetSoloMode` | `void` | int bActivate |
| 754 | `EffectCutSceneHorrified` | `effect` | — |
| 755 | `EffectCutSceneParalyze` | `effect` | — |
| 756 | `EffectCutSceneStunned` | `effect` | — |
| 757 | `CancelPostDialogCharacterSwitch` | `void` | — |
| 758 | `SetMaxHitPoints` | `void` | object oObject, int nMaxHP |
| 759 | `NoClicksFor` | `void` | float fDuration |
| 760 | `HoldWorldFadeInForDialog` | `void` | — |
| 761 | `ShipBuild` | `int` | — |
| 762 | `SurrenderRetainBuffs` | `void` | — |
| 763 | `SuppressStatusSummaryEntry` | `void` | int nNumEntries=1 |
| 764 | `GetCheatCode` | `int` | int nCode |
| 765 | `SetMusicVolume` | `void` | float fVolume=1.0f |
| 766 | `CreateItemOnFloor` | `object` | string sTemplate, location lLocation, int bUseAppearAnimation=FALSE |
| 767 | `SetAvailableNPCId` | `void` | INT nNPC, OBJECT_ID oidNPC |
| 768 | `IsMoviePlaying` | `int` | — |
| 769 | `QueueMovie` | `void` | string sMovie, int bSkippable |
| 770 | `PlayMovieQueue` | `void` | int bAllowSeparateSkips |
| 771 | `YavinHackCloseDoor` | `void` | object oidDoor |

## Generated routine catalog: K2

877 signatures (`data/routines/k2.json`).

| ID | Routine name | Returns | Parameters |
|---:|---|---|---|
| 0 | `Random` | `int` | int nMaxInteger |
| 1 | `PrintString` | `void` | string sString |
| 2 | `PrintFloat` | `void` | float fFloat, int nWidth=18, int nDecimals=9 |
| 3 | `FloatToString` | `string` | float fFloat, int nWidth=18, int nDecimals=9 |
| 4 | `PrintInteger` | `void` | int nInteger |
| 5 | `PrintObject` | `void` | object oObject |
| 6 | `AssignCommand` | `void` | object oActionSubject, action aActionToAssign |
| 7 | `DelayCommand` | `void` | float fSeconds, action aActionToDelay |
| 8 | `ExecuteScript` | `void` | string sScript, object oTarget, int nScriptVar=-1 |
| 9 | `ClearAllActions` | `void` | — |
| 10 | `SetFacing` | `void` | float fDirection |
| 11 | `SwitchPlayerCharacter` | `int` | int nNPC |
| 12 | `SetTime` | `void` | int nHour, int nMinute, int nSecond, int nMillisecond |
| 13 | `SetPartyLeader` | `int` | int nNPC |
| 14 | `SetAreaUnescapable` | `void` | int bUnescapable |
| 15 | `GetAreaUnescapable` | `int` | — |
| 16 | `GetTimeHour` | `int` | — |
| 17 | `GetTimeMinute` | `int` | — |
| 18 | `GetTimeSecond` | `int` | — |
| 19 | `GetTimeMillisecond` | `int` | — |
| 20 | `ActionRandomWalk` | `void` | — |
| 21 | `ActionMoveToLocation` | `void` | location lDestination, int bRun=FALSE |
| 22 | `ActionMoveToObject` | `void` | object oMoveTo, int bRun=FALSE, float fRange=1.0f |
| 23 | `ActionMoveAwayFromObject` | `void` | object oFleeFrom, int bRun=FALSE, float fMoveAwayRange=40.0f |
| 24 | `GetArea` | `object` | object oTarget |
| 25 | `GetEnteringObject` | `object` | — |
| 26 | `GetExitingObject` | `object` | — |
| 27 | `GetPosition` | `vector` | object oTarget |
| 28 | `GetFacing` | `float` | object oTarget |
| 29 | `GetItemPossessor` | `object` | object oItem |
| 30 | `GetItemPossessedBy` | `object` | object oCreature, string sItemTag |
| 31 | `CreateItemOnObject` | `object` | string sItemTemplate, object oTarget=OBJECT_SELF, int nStackSize=1, int nHideMessage=0 |
| 32 | `ActionEquipItem` | `void` | object oItem, int nInventorySlot, int bInstant=FALSE |
| 33 | `ActionUnequipItem` | `void` | object oItem, int bInstant=FALSE |
| 34 | `ActionPickUpItem` | `void` | object oItem |
| 35 | `ActionPutDownItem` | `void` | object oItem |
| 36 | `GetLastAttacker` | `object` | object oAttackee=OBJECT_SELF |
| 37 | `ActionAttack` | `void` | object oAttackee, int bPassive=FALSE |
| 38 | `GetNearestCreature` | `object` | int nFirstCriteriaType, int nFirstCriteriaValue, object oTarget=OBJECT_SELF, int nNth=1, int nSecondCriteriaType=-1, int nSecondCriteriaValue=-1, int nThirdCriteriaType=-1, int nThirdCriteriaValue=-1 |
| 39 | `ActionSpeakString` | `void` | string sStringToSpeak, int nTalkVolume=TALKVOLUME_TALK |
| 40 | `ActionPlayAnimation` | `void` | int nAnimation, float fSpeed=1.0, float fDurationSeconds=0.0 |
| 41 | `GetDistanceToObject` | `float` | object oObject |
| 42 | `GetIsObjectValid` | `int` | object oObject |
| 43 | `ActionOpenDoor` | `void` | object oDoor |
| 44 | `ActionCloseDoor` | `void` | object oDoor |
| 45 | `SetCameraFacing` | `void` | float fDirection |
| 46 | `PlaySound` | `void` | string sSoundName |
| 47 | `GetSpellTargetObject` | `object` | — |
| 48 | `ActionCastSpellAtObject` | `void` | int nSpell, object oTarget, int nMetaMagic=0, int bCheat=FALSE, int nDomainLevel=0, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT, int bInstantSpell=FALSE |
| 49 | `GetCurrentHitPoints` | `int` | object oObject=OBJECT_SELF |
| 50 | `GetMaxHitPoints` | `int` | object oObject=OBJECT_SELF |
| 51 | `EffectAssuredHit` | `effect` | — |
| 52 | `GetLastItemEquipped` | `object` | — |
| 53 | `GetSubScreenID` | `int` | — |
| 54 | `CancelCombat` | `void` | object oidCreature |
| 55 | `GetCurrentForcePoints` | `int` | object oObject=OBJECT_SELF |
| 56 | `GetMaxForcePoints` | `int` | object oObject=OBJECT_SELF |
| 57 | `PauseGame` | `void` | int bPause |
| 58 | `SetPlayerRestrictMode` | `void` | int bRestrict |
| 59 | `GetStringLength` | `int` | string sString |
| 60 | `GetStringUpperCase` | `string` | string sString |
| 61 | `GetStringLowerCase` | `string` | string sString |
| 62 | `GetStringRight` | `string` | string sString, int nCount |
| 63 | `GetStringLeft` | `string` | string sString, int nCount |
| 64 | `InsertString` | `string` | string sDestination, string sString, int nPosition |
| 65 | `GetSubString` | `string` | string sString, int nStart, int nCount |
| 66 | `FindSubString` | `int` | string sString, string sSubString |
| 67 | `fabs` | `float` | float fValue |
| 68 | `cos` | `float` | float fValue |
| 69 | `sin` | `float` | float fValue |
| 70 | `tan` | `float` | float fValue |
| 71 | `acos` | `float` | float fValue |
| 72 | `asin` | `float` | float fValue |
| 73 | `atan` | `float` | float fValue |
| 74 | `log` | `float` | float fValue |
| 75 | `pow` | `float` | float fValue, float fExponent |
| 76 | `sqrt` | `float` | float fValue |
| 77 | `abs` | `int` | int nValue |
| 78 | `EffectHeal` | `effect` | int nDamageToHeal |
| 79 | `EffectDamage` | `effect` | int nDamageAmount, int nDamageType=DAMAGE_TYPE_UNIVERSAL, int nDamagePower=DAMAGE_POWER_NORMAL |
| 80 | `EffectAbilityIncrease` | `effect` | int nAbilityToIncrease, int nModifyBy |
| 81 | `EffectDamageResistance` | `effect` | int nDamageType, int nAmount, int nLimit=0 |
| 82 | `EffectResurrection` | `effect` | int nHPPercent=0 |
| 83 | `GetPlayerRestrictMode` | `int` | object oObject=OBJECT_SELF |
| 84 | `GetCasterLevel` | `int` | object oCreature |
| 85 | `GetFirstEffect` | `effect` | object oCreature |
| 86 | `GetNextEffect` | `effect` | object oCreature |
| 87 | `RemoveEffect` | `void` | object oCreature, effect eEffect |
| 88 | `GetIsEffectValid` | `int` | effect eEffect |
| 89 | `GetEffectDurationType` | `int` | effect eEffect |
| 90 | `GetEffectSubType` | `int` | effect eEffect |
| 91 | `GetEffectCreator` | `object` | effect eEffect |
| 92 | `IntToString` | `string` | int nInteger |
| 93 | `GetFirstObjectInArea` | `object` | object oArea=OBJECT_INVALID, int nObjectFilter=OBJECT_TYPE_CREATURE |
| 94 | `GetNextObjectInArea` | `object` | object oArea=OBJECT_INVALID, int nObjectFilter=OBJECT_TYPE_CREATURE |
| 95 | `d2` | `int` | int nNumDice=1 |
| 96 | `d3` | `int` | int nNumDice=1 |
| 97 | `d4` | `int` | int nNumDice=1 |
| 98 | `d6` | `int` | int nNumDice=1 |
| 99 | `d8` | `int` | int nNumDice=1 |
| 100 | `d10` | `int` | int nNumDice=1 |
| 101 | `d12` | `int` | int nNumDice=1 |
| 102 | `d20` | `int` | int nNumDice=1 |
| 103 | `d100` | `int` | int nNumDice=1 |
| 104 | `VectorMagnitude` | `float` | vector vVector |
| 105 | `GetMetaMagicFeat` | `int` | — |
| 106 | `GetObjectType` | `int` | object oTarget |
| 107 | `GetRacialType` | `int` | object oCreature |
| 108 | `FortitudeSave` | `int` | object oCreature, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 109 | `ReflexSave` | `int` | object oCreature, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 110 | `WillSave` | `int` | object oCreature, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 111 | `GetSpellSaveDC` | `int` | — |
| 112 | `MagicalEffect` | `effect` | effect eEffect |
| 113 | `SupernaturalEffect` | `effect` | effect eEffect |
| 114 | `ExtraordinaryEffect` | `effect` | effect eEffect |
| 115 | `EffectACIncrease` | `effect` | int nValue, int nModifyType=AC_DODGE_BONUS, int nDamageType=AC_VS_DAMAGE_TYPE_ALL |
| 116 | `GetAC` | `int` | object oObject, int nForFutureUse=0 |
| 117 | `EffectSavingThrowIncrease` | `effect` | int nSave, int nValue, int nSaveType=SAVING_THROW_TYPE_ALL |
| 118 | `EffectAttackIncrease` | `effect` | int nBonus, int nModifierType=ATTACK_BONUS_MISC |
| 119 | `EffectDamageReduction` | `effect` | int nAmount, int nDamagePower, int nLimit=0 |
| 120 | `EffectDamageIncrease` | `effect` | int nBonus, int nDamageType=DAMAGE_TYPE_UNIVERSAL |
| 121 | `RoundsToSeconds` | `float` | int nRounds |
| 122 | `HoursToSeconds` | `float` | int nHours |
| 123 | `TurnsToSeconds` | `float` | int nTurns |
| 124 | `SoundObjectSetFixedVariance` | `void` | object oSound, float fFixedVariance |
| 125 | `GetGoodEvilValue` | `int` | object oCreature |
| 126 | `GetPartyMemberCount` | `int` | — |
| 127 | `GetAlignmentGoodEvil` | `int` | object oCreature |
| 128 | `GetFirstObjectInShape` | `object` | int nShape, float fSize, location lTarget, int bLineOfSight=FALSE, int nObjectFilter=OBJECT_TYPE_CREATURE, vector vOrigin=[0.0,0.0,0.0] |
| 129 | `GetNextObjectInShape` | `object` | int nShape, float fSize, location lTarget, int bLineOfSight=FALSE, int nObjectFilter=OBJECT_TYPE_CREATURE, vector vOrigin=[0.0,0.0,0.0] |
| 130 | `EffectEntangle` | `effect` | — |
| 131 | `SignalEvent` | `void` | object oObject, event evToRun |
| 132 | `EventUserDefined` | `event` | int nUserDefinedEventNumber |
| 133 | `EffectDeath` | `effect` | int nSpectacularDeath=FALSE, int nDisplayFeedback=TRUE, int nNoFadeAway=FALSE |
| 134 | `EffectKnockdown` | `effect` | — |
| 135 | `ActionGiveItem` | `void` | object oItem, object oGiveTo |
| 136 | `ActionTakeItem` | `void` | object oItem, object oTakeFrom |
| 137 | `VectorNormalize` | `vector` | vector vVector |
| 138 | `GetItemStackSize` | `int` | object oItem |
| 139 | `GetAbilityScore` | `int` | object oCreature, int nAbilityType |
| 140 | `GetIsDead` | `int` | object oCreature |
| 141 | `PrintVector` | `void` | vector vVector, int bPrepend |
| 142 | `Vector` | `vector` | float x=0.0f, float y=0.0f, float z=0.0f |
| 143 | `SetFacingPoint` | `void` | vector vTarget |
| 144 | `AngleToVector` | `vector` | float fAngle |
| 145 | `VectorToAngle` | `float` | vector vVector |
| 146 | `TouchAttackMelee` | `int` | object oTarget, int bDisplayFeedback=TRUE |
| 147 | `TouchAttackRanged` | `int` | object oTarget, int bDisplayFeedback=TRUE |
| 148 | `EffectParalyze` | `effect` | — |
| 149 | `EffectSpellImmunity` | `effect` | int nImmunityToSpell=FORCE_POWER_ALL_FORCE_POWERS |
| 150 | `SetItemStackSize` | `void` | object oItem, int nStackSize |
| 151 | `GetDistanceBetween` | `float` | object oObjectA, object oObjectB |
| 152 | `SetReturnStrref` | `void` | int bShow, int srStringRef=0, int srReturnQueryStrRef=0 |
| 153 | `EffectForceJump` | `effect` | object oTarget, int nAdvanced=0 |
| 154 | `EffectSleep` | `effect` | — |
| 155 | `GetItemInSlot` | `object` | int nInventorySlot, object oCreature=OBJECT_SELF |
| 156 | `EffectTemporaryForcePoints` | `effect` | int nTempForce |
| 157 | `EffectConfused` | `effect` | — |
| 158 | `EffectFrightened` | `effect` | — |
| 159 | `EffectChoke` | `effect` | — |
| 160 | `SetGlobalString` | `void` | string sIdentifier, string sValue |
| 161 | `EffectStunned` | `effect` | — |
| 162 | `SetCommandable` | `void` | int bCommandable, object oTarget=OBJECT_SELF |
| 163 | `GetCommandable` | `int` | object oTarget=OBJECT_SELF |
| 164 | `EffectRegenerate` | `effect` | int nAmount, float fIntervalSeconds |
| 165 | `EffectMovementSpeedIncrease` | `effect` | int nNewSpeedPercent |
| 166 | `GetHitDice` | `int` | object oCreature |
| 167 | `ActionForceFollowObject` | `void` | object oFollow, float fFollowDistance=0.0f |
| 168 | `GetTag` | `string` | object oObject |
| 169 | `ResistForce` | `int` | object oSource, object oTarget |
| 170 | `GetEffectType` | `int` | effect eEffect |
| 171 | `EffectAreaOfEffect` | `effect` | int nAreaEffectId, string sOnEnterScript="", string sHeartbeatScript="", string sOnExitScript="" |
| 172 | `GetFactionEqual` | `int` | object oFirstObject, object oSecondObject=OBJECT_SELF |
| 173 | `ChangeFaction` | `void` | object oObjectToChangeFaction, object oMemberOfFactionToJoin |
| 174 | `GetIsListening` | `int` | object oObject |
| 175 | `SetListening` | `void` | object oObject, int bValue |
| 176 | `SetListenPattern` | `void` | object oObject, string sPattern, int nNumber=0 |
| 177 | `TestStringAgainstPattern` | `int` | string sPattern, string sStringToTest |
| 178 | `GetMatchedSubstring` | `string` | int nString |
| 179 | `GetMatchedSubstringsCount` | `int` | — |
| 180 | `EffectVisualEffect` | `effect` | int nVisualEffectId, int nMissEffect=FALSE |
| 181 | `GetFactionWeakestMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 182 | `GetFactionStrongestMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 183 | `GetFactionMostDamagedMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 184 | `GetFactionLeastDamagedMember` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 185 | `GetFactionGold` | `int` | object oFactionMember |
| 186 | `GetFactionAverageReputation` | `int` | object oSourceFactionMember, object oTarget |
| 187 | `GetFactionAverageGoodEvilAlignment` | `int` | object oFactionMember |
| 188 | `SoundObjectGetFixedVariance` | `float` | object oSound |
| 189 | `GetFactionAverageLevel` | `int` | object oFactionMember |
| 190 | `GetFactionAverageXP` | `int` | object oFactionMember |
| 191 | `GetFactionMostFrequentClass` | `int` | object oFactionMember |
| 192 | `GetFactionWorstAC` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 193 | `GetFactionBestAC` | `object` | object oFactionMember=OBJECT_SELF, int bMustBeVisible=TRUE |
| 194 | `GetGlobalString` | `string` | string sIdentifier |
| 195 | `GetListenPatternNumber` | `int` | — |
| 196 | `ActionJumpToObject` | `void` | object oToJumpTo, int bWalkStraightLineToPoint=TRUE |
| 197 | `GetWaypointByTag` | `object` | string sWaypointTag |
| 198 | `GetTransitionTarget` | `object` | object oTransition |
| 199 | `EffectLinkEffects` | `effect` | effect eChildEffect, effect eParentEffect |
| 200 | `GetObjectByTag` | `object` | string sTag, int nNth=0 |
| 201 | `AdjustAlignment` | `void` | object oSubject, int nAlignment, int nShift, int bDontModifyNPCs=FALSE |
| 202 | `ActionWait` | `void` | float fSeconds |
| 203 | `SetAreaTransitionBMP` | `void` | int nPredefinedAreaTransition, string sCustomAreaTransitionBMP="" |
| 204 | `ActionStartConversation` | `void` | object oObjectToConverse, string sDialogResRef="", int bPrivateConversation=FALSE, int nConversationType=CONVERSATION_TYPE_CINEMATIC, int bIgnoreStartRange=FALSE, string sNameObjectToIgnore1="", string sNameObjectToIgnore2="", string sNameObjectToIgnore3="", string sNameObjectToIgnore4="", string sNameObjectToIgnore5="", string sNameObjectToIgnore6="", int bUseLeader=FALSE, int nBarkX=-1, int nBarkY=-1, int bDontClearAllActions=0 |
| 205 | `ActionPauseConversation` | `void` | — |
| 206 | `ActionResumeConversation` | `void` | — |
| 207 | `EffectBeam` | `effect` | int nBeamVisualEffect, object oEffector, int nBodyPart, int bMissEffect=FALSE |
| 208 | `GetReputation` | `int` | object oSource, object oTarget |
| 209 | `AdjustReputation` | `void` | object oTarget, object oSourceFactionMember, int nAdjustment |
| 210 | `GetModuleFileName` | `string` | — |
| 211 | `GetGoingToBeAttackedBy` | `object` | object oTarget |
| 212 | `EffectForceResistanceIncrease` | `effect` | int nValue |
| 213 | `GetLocation` | `location` | object oObject |
| 214 | `ActionJumpToLocation` | `void` | location lLocation |
| 215 | `Location` | `location` | vector vPosition, float fOrientation |
| 216 | `ApplyEffectAtLocation` | `void` | int nDurationType, effect eEffect, location lLocation, float fDuration=0.0f |
| 217 | `GetIsPC` | `int` | object oCreature |
| 218 | `FeetToMeters` | `float` | float fFeet |
| 219 | `YardsToMeters` | `float` | float fYards |
| 220 | `ApplyEffectToObject` | `void` | int nDurationType, effect eEffect, object oTarget, float fDuration=0.0f |
| 221 | `SpeakString` | `void` | string sStringToSpeak, int nTalkVolume=TALKVOLUME_TALK |
| 222 | `GetSpellTargetLocation` | `location` | — |
| 223 | `GetPositionFromLocation` | `vector` | location lLocation |
| 224 | `EffectBodyFuel` | `effect` | — |
| 225 | `GetFacingFromLocation` | `float` | location lLocation |
| 226 | `GetNearestCreatureToLocation` | `object` | int nFirstCriteriaType, int nFirstCriteriaValue, location lLocation, int nNth=1, int nSecondCriteriaType=-1, int nSecondCriteriaValue=-1, int nThirdCriteriaType=-1, int nThirdCriteriaValue=-1 |
| 227 | `GetNearestObject` | `object` | int nObjectType=OBJECT_TYPE_ALL, object oTarget=OBJECT_SELF, int nNth=1 |
| 228 | `GetNearestObjectToLocation` | `object` | int nObjectType, location lLocation, int nNth=1 |
| 229 | `GetNearestObjectByTag` | `object` | string sTag, object oTarget=OBJECT_SELF, int nNth=1 |
| 230 | `IntToFloat` | `float` | int nInteger |
| 231 | `FloatToInt` | `int` | float fFloat |
| 232 | `StringToInt` | `int` | string sNumber |
| 233 | `StringToFloat` | `float` | string sNumber |
| 234 | `ActionCastSpellAtLocation` | `void` | int nSpell, location lTargetLocation, int nMetaMagic=0, int bCheat=FALSE, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT, int bInstantSpell=FALSE |
| 235 | `GetIsEnemy` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 236 | `GetIsFriend` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 237 | `GetIsNeutral` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 238 | `GetPCSpeaker` | `object` | — |
| 239 | `GetStringByStrRef` | `string` | int nStrRef |
| 240 | `ActionSpeakStringByStrRef` | `void` | int nStrRef, int nTalkVolume=TALKVOLUME_TALK |
| 241 | `DestroyObject` | `void` | object oDestroy, float fDelay=0.0f, int bNoFade=FALSE, float fDelayUntilFade=0.0f, int nHideFeedback=0 |
| 242 | `GetModule` | `object` | — |
| 243 | `CreateObject` | `object` | int nObjectType, string sTemplate, location lLocation, int bUseAppearAnimation=FALSE |
| 244 | `EventSpellCastAt` | `event` | object oCaster, int nSpell, int bHarmful=TRUE |
| 245 | `GetLastSpellCaster` | `object` | — |
| 246 | `GetLastSpell` | `int` | — |
| 247 | `GetUserDefinedEventNumber` | `int` | — |
| 248 | `GetSpellId` | `int` | — |
| 249 | `RandomName` | `string` | — |
| 250 | `EffectPoison` | `effect` | int nPoisonType |
| 251 | `GetLoadFromSaveGame` | `int` | — |
| 252 | `EffectAssuredDeflection` | `effect` | int nReturn=0 |
| 253 | `GetName` | `string` | object oObject |
| 254 | `GetLastSpeaker` | `object` | — |
| 255 | `BeginConversation` | `int` | string sResRef="", object oObjectToDialog=OBJECT_INVALID |
| 256 | `GetLastPerceived` | `object` | — |
| 257 | `GetLastPerceptionHeard` | `int` | — |
| 258 | `GetLastPerceptionInaudible` | `int` | — |
| 259 | `GetLastPerceptionSeen` | `int` | — |
| 260 | `GetLastClosedBy` | `object` | — |
| 261 | `GetLastPerceptionVanished` | `int` | — |
| 262 | `GetFirstInPersistentObject` | `object` | object oPersistentObject=OBJECT_SELF, int nResidentObjectType=OBJECT_TYPE_CREATURE, int nPersistentZone=PERSISTENT_ZONE_ACTIVE |
| 263 | `GetNextInPersistentObject` | `object` | object oPersistentObject=OBJECT_SELF, int nResidentObjectType=OBJECT_TYPE_CREATURE, int nPersistentZone=PERSISTENT_ZONE_ACTIVE |
| 264 | `GetAreaOfEffectCreator` | `object` | object oAreaOfEffectObject=OBJECT_SELF |
| 265 | `ShowLevelUpGUI` | `int` | — |
| 266 | `SetItemNonEquippable` | `void` | object oItem, int bNonEquippable |
| 267 | `GetButtonMashCheck` | `int` | — |
| 268 | `SetButtonMashCheck` | `void` | int nCheck |
| 269 | `EffectForcePushTargeted` | `effect` | location lCentre, int nIgnoreTestDirectLine=0 |
| 270 | `EffectHaste` | `effect` | — |
| 271 | `GiveItem` | `void` | object oItem, object oGiveTo |
| 272 | `ObjectToString` | `string` | object oObject |
| 273 | `EffectImmunity` | `effect` | int nImmunityType |
| 274 | `GetIsImmune` | `int` | object oCreature, int nImmunityType, object oVersus=OBJECT_INVALID |
| 275 | `EffectDamageImmunityIncrease` | `effect` | int nDamageType, int nPercentImmunity |
| 276 | `GetEncounterActive` | `int` | object oEncounter=OBJECT_SELF |
| 277 | `SetEncounterActive` | `void` | int nNewValue, object oEncounter=OBJECT_SELF |
| 278 | `GetEncounterSpawnsMax` | `int` | object oEncounter=OBJECT_SELF |
| 279 | `SetEncounterSpawnsMax` | `void` | int nNewValue, object oEncounter=OBJECT_SELF |
| 280 | `GetEncounterSpawnsCurrent` | `int` | object oEncounter=OBJECT_SELF |
| 281 | `SetEncounterSpawnsCurrent` | `void` | int nNewValue, object oEncounter=OBJECT_SELF |
| 282 | `GetModuleItemAcquired` | `object` | — |
| 283 | `GetModuleItemAcquiredFrom` | `object` | — |
| 284 | `SetCustomToken` | `void` | int nCustomTokenNumber, string sTokenValue |
| 285 | `GetHasFeat` | `int` | int nFeat, object oCreature=OBJECT_SELF |
| 286 | `GetHasSkill` | `int` | int nSkill, object oCreature=OBJECT_SELF |
| 287 | `ActionUseFeat` | `void` | int nFeat, object oTarget |
| 288 | `ActionUseSkill` | `void` | int nSkill, object oTarget, int nSubSkill=0, object oItemUsed=OBJECT_INVALID |
| 289 | `GetObjectSeen` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 290 | `GetObjectHeard` | `int` | object oTarget, object oSource=OBJECT_SELF |
| 291 | `GetLastPlayerDied` | `object` | — |
| 292 | `GetModuleItemLost` | `object` | — |
| 293 | `GetModuleItemLostBy` | `object` | — |
| 294 | `ActionDoCommand` | `void` | action aActionToDo |
| 295 | `EventConversation` | `event` | — |
| 296 | `SetEncounterDifficulty` | `void` | int nEncounterDifficulty, object oEncounter=OBJECT_SELF |
| 297 | `GetEncounterDifficulty` | `int` | object oEncounter=OBJECT_SELF |
| 298 | `GetDistanceBetweenLocations` | `float` | location lLocationA, location lLocationB |
| 299 | `GetReflexAdjustedDamage` | `int` | int nDamage, object oTarget, int nDC, int nSaveType=SAVING_THROW_TYPE_NONE, object oSaveVersus=OBJECT_SELF |
| 300 | `PlayAnimation` | `void` | int nAnimation, float fSpeed=1.0, float fSeconds=0.0 |
| 301 | `TalentSpell` | `talent` | int nSpell |
| 302 | `TalentFeat` | `talent` | int nFeat |
| 303 | `TalentSkill` | `talent` | int nSkill |
| 304 | `GetHasSpellEffect` | `int` | int nSpell, object oObject=OBJECT_SELF |
| 305 | `GetEffectSpellId` | `int` | effect eSpellEffect |
| 306 | `GetCreatureHasTalent` | `int` | talent tTalent, object oCreature=OBJECT_SELF |
| 307 | `GetCreatureTalentRandom` | `talent` | int nCategory, object oCreature=OBJECT_SELF, int nInclusion=0 |
| 308 | `GetCreatureTalentBest` | `talent` | int nCategory, int nCRMax, object oCreature=OBJECT_SELF, int nInclusion=0, int nExcludeType=-1, int nExcludeId=-1 |
| 309 | `ActionUseTalentOnObject` | `void` | talent tChosenTalent, object oTarget |
| 310 | `ActionUseTalentAtLocation` | `void` | talent tChosenTalent, location lTargetLocation |
| 311 | `GetGoldPieceValue` | `int` | object oItem |
| 312 | `GetIsPlayableRacialType` | `int` | object oCreature |
| 313 | `JumpToLocation` | `void` | location lDestination |
| 314 | `EffectTemporaryHitpoints` | `effect` | int nHitPoints |
| 315 | `GetSkillRank` | `int` | int nSkill, object oTarget=OBJECT_SELF |
| 316 | `GetAttackTarget` | `object` | object oCreature=OBJECT_SELF |
| 317 | `GetLastAttackType` | `int` | object oCreature=OBJECT_SELF |
| 318 | `GetLastAttackMode` | `int` | object oCreature=OBJECT_SELF |
| 319 | `GetDistanceBetween2D` | `float` | object oObjectA, object oObjectB |
| 320 | `GetIsInCombat` | `int` | object oCreature=OBJECT_SELF, int bOnlyCountReal=FALSE |
| 321 | `GetLastAssociateCommand` | `int` | object oAssociate=OBJECT_SELF |
| 322 | `GiveGoldToCreature` | `void` | object oCreature, int nGP |
| 323 | `SetIsDestroyable` | `void` | int bDestroyable, int bRaiseable=TRUE, int bSelectableWhenDead=FALSE |
| 324 | `SetLocked` | `void` | object oTarget, int bLocked |
| 325 | `GetLocked` | `int` | object oTarget |
| 326 | `GetClickingObject` | `object` | — |
| 327 | `SetAssociateListenPatterns` | `void` | object oTarget=OBJECT_SELF |
| 328 | `GetLastWeaponUsed` | `object` | object oCreature |
| 329 | `ActionInteractObject` | `void` | object oPlaceable |
| 330 | `GetLastUsedBy` | `object` | — |
| 331 | `GetAbilityModifier` | `int` | int nAbility, object oCreature=OBJECT_SELF |
| 332 | `GetIdentified` | `int` | object oItem |
| 333 | `SetIdentified` | `void` | object oItem, int bIdentified |
| 334 | `GetDistanceBetweenLocations2D` | `float` | location lLocationA, location lLocationB |
| 335 | `GetDistanceToObject2D` | `float` | object oObject |
| 336 | `GetBlockingDoor` | `object` | — |
| 337 | `GetIsDoorActionPossible` | `int` | object oTargetDoor, int nDoorAction |
| 338 | `DoDoorAction` | `void` | object oTargetDoor, int nDoorAction |
| 339 | `GetFirstItemInInventory` | `object` | object oTarget=OBJECT_SELF |
| 340 | `GetNextItemInInventory` | `object` | object oTarget=OBJECT_SELF |
| 341 | `GetClassByPosition` | `int` | int nClassPosition, object oCreature=OBJECT_SELF |
| 342 | `GetLevelByPosition` | `int` | int nClassPosition, object oCreature=OBJECT_SELF |
| 343 | `GetLevelByClass` | `int` | int nClassType, object oCreature=OBJECT_SELF |
| 344 | `GetDamageDealtByType` | `int` | int nDamageType |
| 345 | `GetTotalDamageDealt` | `int` | — |
| 346 | `GetLastDamager` | `object` | — |
| 347 | `GetLastDisarmed` | `object` | — |
| 348 | `GetLastDisturbed` | `object` | — |
| 349 | `GetLastLocked` | `object` | — |
| 350 | `GetLastUnlocked` | `object` | — |
| 351 | `EffectSkillIncrease` | `effect` | int nSkill, int nValue |
| 352 | `GetInventoryDisturbType` | `int` | — |
| 353 | `GetInventoryDisturbItem` | `object` | — |
| 354 | `ShowUpgradeScreen` | `void` | object oItem=OBJECT_INVALID, object oCharacter=OBJECT_INVALID, int nDisableItemCreation=FALSE, int nDisableUpgrade=FALSE, string sOverride2DA="" |
| 355 | `VersusAlignmentEffect` | `effect` | effect eEffect, int nLawChaos=ALIGNMENT_ALL, int nGoodEvil=ALIGNMENT_ALL |
| 356 | `VersusRacialTypeEffect` | `effect` | effect eEffect, int nRacialType |
| 357 | `VersusTrapEffect` | `effect` | effect eEffect |
| 358 | `GetGender` | `int` | object oCreature |
| 359 | `GetIsTalentValid` | `int` | talent tTalent |
| 360 | `ActionMoveAwayFromLocation` | `void` | location lMoveAwayFrom, int bRun=FALSE, float fMoveAwayRange=40.0f |
| 361 | `GetAttemptedAttackTarget` | `object` | — |
| 362 | `GetTypeFromTalent` | `int` | talent tTalent |
| 363 | `GetIdFromTalent` | `int` | talent tTalent |
| 364 | `PlayPazaak` | `void` | int nOpponentPazaakDeck, string sEndScript, int nMaxWager, int bShowTutorial=FALSE, object oOpponent=OBJECT_INVALID |
| 365 | `GetLastPazaakResult` | `int` | — |
| 366 | `DisplayFeedBackText` | `void` | object oCreature, int nTextConstant |
| 367 | `AddJournalQuestEntry` | `void` | string szPlotID, int nState, int bAllowOverrideHigher=FALSE |
| 368 | `RemoveJournalQuestEntry` | `void` | string szPlotID |
| 369 | `GetJournalEntry` | `int` | string szPlotID |
| 370 | `PlayRumblePattern` | `int` | int nPattern |
| 371 | `StopRumblePattern` | `int` | int nPattern |
| 372 | `EffectDamageForcePoints` | `effect` | int nDamage |
| 373 | `EffectHealForcePoints` | `effect` | int nHeal |
| 374 | `SendMessageToPC` | `void` | object oPlayer, string szMessage |
| 375 | `GetAttemptedSpellTarget` | `object` | — |
| 376 | `GetLastOpenedBy` | `object` | — |
| 377 | `GetHasSpell` | `int` | int nSpell, object oCreature=OBJECT_SELF |
| 378 | `OpenStore` | `void` | object oStore, object oPC, int nBonusMarkUp=0, int nBonusMarkDown=0 |
| 379 | `ActionSurrenderToEnemies` | `void` | — |
| 380 | `GetFirstFactionMember` | `object` | object oMemberOfFaction, int bPCOnly=TRUE |
| 381 | `GetNextFactionMember` | `object` | object oMemberOfFaction, int bPCOnly=TRUE |
| 382 | `ActionForceMoveToLocation` | `void` | location lDestination, int bRun=FALSE, float fTimeout=30.0f |
| 383 | `ActionForceMoveToObject` | `void` | object oMoveTo, int bRun=FALSE, float fRange=1.0f, float fTimeout=30.0f |
| 384 | `GetJournalQuestExperience` | `int` | string szPlotID |
| 385 | `JumpToObject` | `void` | object oToJumpTo, int nWalkStraightLineToPoint=1 |
| 386 | `SetMapPinEnabled` | `void` | object oMapPin, int nEnabled |
| 387 | `EffectHitPointChangeWhenDying` | `effect` | float fHitPointChangePerRound |
| 388 | `PopUpGUIPanel` | `void` | object oPC, int nGUIPanel |
| 389 | `AddMultiClass` | `void` | int nClassType, object oSource |
| 390 | `GetIsLinkImmune` | `int` | object oTarget, effect eEffect |
| 391 | `EffectDroidStun` | `effect` | — |
| 392 | `EffectForcePushed` | `effect` | — |
| 393 | `GiveXPToCreature` | `void` | object oCreature, int nXpAmount |
| 394 | `SetXP` | `void` | object oCreature, int nXpAmount |
| 395 | `GetXP` | `int` | object oCreature |
| 396 | `IntToHexString` | `string` | int nInteger |
| 397 | `GetBaseItemType` | `int` | object oItem |
| 398 | `GetItemHasItemProperty` | `int` | object oItem, int nProperty |
| 399 | `ActionEquipMostDamagingMelee` | `void` | object oVersus=OBJECT_INVALID, int bOffHand=FALSE |
| 400 | `ActionEquipMostDamagingRanged` | `void` | object oVersus=OBJECT_INVALID |
| 401 | `GetItemACValue` | `int` | object oItem |
| 402 | `EffectForceResisted` | `effect` | object oSource |
| 403 | `ExploreAreaForPlayer` | `void` | object oArea, object oPlayer |
| 404 | `ActionEquipMostEffectiveArmor` | `void` | — |
| 405 | `GetIsDay` | `int` | — |
| 406 | `GetIsNight` | `int` | — |
| 407 | `GetIsDawn` | `int` | — |
| 408 | `GetIsDusk` | `int` | — |
| 409 | `GetIsEncounterCreature` | `int` | object oCreature=OBJECT_SELF |
| 410 | `GetLastPlayerDying` | `object` | — |
| 411 | `GetStartingLocation` | `location` | — |
| 412 | `ChangeToStandardFaction` | `void` | object oCreatureToChange, int nStandardFaction |
| 413 | `SoundObjectPlay` | `void` | object oSound |
| 414 | `SoundObjectStop` | `void` | object oSound |
| 415 | `SoundObjectSetVolume` | `void` | object oSound, int nVolume |
| 416 | `SoundObjectSetPosition` | `void` | object oSound, vector vPosition |
| 417 | `SpeakOneLinerConversation` | `void` | string sDialogResRef="", object oTokenTarget=OBJECT_TYPE_INVALID |
| 418 | `GetGold` | `int` | object oTarget=OBJECT_SELF |
| 419 | `GetLastRespawnButtonPresser` | `object` | — |
| 420 | `EffectForceFizzle` | `effect` | — |
| 421 | `SetLightsaberPowered` | `void` | object oCreature, int bOverride, int bPowered=TRUE, int bShowTransition=FALSE |
| 422 | `GetIsWeaponEffective` | `int` | object oVersus=OBJECT_INVALID, int bOffHand=FALSE |
| 423 | `GetLastSpellHarmful` | `int` | — |
| 424 | `EventActivateItem` | `event` | object oItem, location lTarget, object oTarget=OBJECT_INVALID |
| 425 | `MusicBackgroundPlay` | `void` | object oArea |
| 426 | `MusicBackgroundStop` | `void` | object oArea |
| 427 | `MusicBackgroundSetDelay` | `void` | object oArea, int nDelay |
| 428 | `MusicBackgroundChangeDay` | `void` | object oArea, int nTrack, int nStreamingMusic=FALSE |
| 429 | `MusicBackgroundChangeNight` | `void` | object oArea, int nTrack, int nStreamingMusic=FALSE |
| 430 | `MusicBattlePlay` | `void` | object oArea |
| 431 | `MusicBattleStop` | `void` | object oArea |
| 432 | `MusicBattleChange` | `void` | object oArea, int nTrack |
| 433 | `AmbientSoundPlay` | `void` | object oArea |
| 434 | `AmbientSoundStop` | `void` | object oArea |
| 435 | `AmbientSoundChangeDay` | `void` | object oArea, int nTrack |
| 436 | `AmbientSoundChangeNight` | `void` | object oArea, int nTrack |
| 437 | `GetLastKiller` | `object` | — |
| 438 | `GetSpellCastItem` | `object` | — |
| 439 | `GetItemActivated` | `object` | — |
| 440 | `GetItemActivator` | `object` | — |
| 441 | `GetItemActivatedTargetLocation` | `location` | — |
| 442 | `GetItemActivatedTarget` | `object` | — |
| 443 | `GetIsOpen` | `int` | object oObject |
| 444 | `TakeGoldFromCreature` | `void` | int nAmount, object oCreatureToTakeFrom, int bDestroy=FALSE |
| 445 | `GetIsInConversation` | `int` | object oObject |
| 446 | `EffectAbilityDecrease` | `effect` | int nAbility, int nModifyBy |
| 447 | `EffectAttackDecrease` | `effect` | int nPenalty, int nModifierType=ATTACK_BONUS_MISC |
| 448 | `EffectDamageDecrease` | `effect` | int nPenalty, int nDamageType=DAMAGE_TYPE_UNIVERSAL |
| 449 | `EffectDamageImmunityDecrease` | `effect` | int nDamageType, int nPercentImmunity |
| 450 | `EffectACDecrease` | `effect` | int nValue, int nModifyType=AC_DODGE_BONUS, int nDamageType=AC_VS_DAMAGE_TYPE_ALL |
| 451 | `EffectMovementSpeedDecrease` | `effect` | int nPercentChange |
| 452 | `EffectSavingThrowDecrease` | `effect` | int nSave, int nValue, int nSaveType=SAVING_THROW_TYPE_ALL |
| 453 | `EffectSkillDecrease` | `effect` | int nSkill, int nValue |
| 454 | `EffectForceResistanceDecrease` | `effect` | int nValue |
| 455 | `GetPlotFlag` | `int` | object oTarget=OBJECT_SELF |
| 456 | `SetPlotFlag` | `void` | object oTarget, int nPlotFlag |
| 457 | `EffectInvisibility` | `effect` | int nInvisibilityType |
| 458 | `EffectConcealment` | `effect` | int nPercentage |
| 459 | `EffectForceShield` | `effect` | int nShield |
| 460 | `EffectDispelMagicAll` | `effect` | int nCasterLevel |
| 461 | `SetDialogPlaceableCamera` | `void` | int nCameraId |
| 462 | `GetSoloMode` | `int` | — |
| 463 | `EffectDisguise` | `effect` | int nDisguiseAppearance |
| 464 | `GetMaxStealthXP` | `int` | — |
| 465 | `EffectTrueSeeing` | `effect` | — |
| 466 | `EffectSeeInvisible` | `effect` | — |
| 467 | `EffectTimeStop` | `effect` | — |
| 468 | `SetMaxStealthXP` | `void` | int nMax |
| 469 | `EffectBlasterDeflectionIncrease` | `effect` | int nChange |
| 470 | `EffectBlasterDeflectionDecrease` | `effect` | int nChange |
| 471 | `EffectHorrified` | `effect` | — |
| 472 | `EffectSpellLevelAbsorption` | `effect` | int nMaxSpellLevelAbsorbed, int nTotalSpellLevelsAbsorbed=0, int nSpellSchool=0 |
| 473 | `EffectDispelMagicBest` | `effect` | int nCasterLevel |
| 474 | `GetCurrentStealthXP` | `int` | — |
| 475 | `GetNumStackedItems` | `int` | object oItem |
| 476 | `SurrenderToEnemies` | `void` | — |
| 477 | `EffectMissChance` | `effect` | int nPercentage |
| 478 | `SetCurrentStealthXP` | `void` | int nCurrent |
| 479 | `GetCreatureSize` | `int` | object oCreature |
| 480 | `AwardStealthXP` | `void` | object oTarget |
| 481 | `GetStealthXPEnabled` | `int` | — |
| 482 | `SetStealthXPEnabled` | `void` | int bEnabled |
| 483 | `ActionUnlockObject` | `void` | object oTarget |
| 484 | `ActionLockObject` | `void` | object oTarget |
| 485 | `EffectModifyAttacks` | `effect` | int nAttacks |
| 486 | `GetLastTrapDetected` | `object` | object oTarget=OBJECT_SELF |
| 487 | `EffectDamageShield` | `effect` | int nDamageAmount, int nRandomAmount, int nDamageType |
| 488 | `GetNearestTrapToObject` | `object` | object oTarget=OBJECT_SELF, int nTrapDetected=TRUE |
| 489 | `GetAttemptedMovementTarget` | `object` | — |
| 490 | `GetBlockingCreature` | `object` | object oTarget=OBJECT_SELF |
| 491 | `GetFortitudeSavingThrow` | `int` | object oTarget |
| 492 | `GetWillSavingThrow` | `int` | object oTarget |
| 493 | `GetReflexSavingThrow` | `int` | object oTarget |
| 494 | `GetChallengeRating` | `float` | object oCreature |
| 495 | `GetFoundEnemyCreature` | `object` | object oTarget=OBJECT_SELF |
| 496 | `GetMovementRate` | `int` | object oCreature |
| 497 | `GetSubRace` | `int` | object oCreature |
| 498 | `GetStealthXPDecrement` | `int` | — |
| 499 | `SetStealthXPDecrement` | `void` | int nDecrement |
| 500 | `DuplicateHeadAppearance` | `void` | object oidCreatureToChange, object oidCreatureToMatch |
| 501 | `ActionCastFakeSpellAtObject` | `void` | int nSpell, object oTarget, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT |
| 502 | `ActionCastFakeSpellAtLocation` | `void` | int nSpell, location lTarget, int nProjectilePathType=PROJECTILE_PATH_TYPE_DEFAULT |
| 503 | `CutsceneAttack` | `void` | object oTarget, int nAnimation, int nAttackResult, int nDamage |
| 504 | `SetCameraMode` | `void` | object oPlayer, int nCameraMode |
| 505 | `SetLockOrientationInDialog` | `void` | object oObject, int nValue |
| 506 | `SetLockHeadFollowInDialog` | `void` | object oObject, int nValue |
| 507 | `CutsceneMove` | `void` | object oObject, vector vPosition, int nRun |
| 508 | `EnableVideoEffect` | `void` | int nEffectType |
| 509 | `StartNewModule` | `void` | string sModuleName, string sWayPoint="", string sMovie1="", string sMovie2="", string sMovie3="", string sMovie4="", string sMovie5="", string sMovie6="" |
| 510 | `DisableVideoEffect` | `void` | — |
| 511 | `GetWeaponRanged` | `int` | object oItem |
| 512 | `DoSinglePlayerAutoSave` | `void` | — |
| 513 | `GetGameDifficulty` | `int` | — |
| 514 | `GetUserActionsPending` | `int` | — |
| 515 | `RevealMap` | `void` | vector vPoint=[0.0,0.0,0.0], int nRadius=-1 |
| 516 | `SetTutorialWindowsEnabled` | `void` | int bEnabled |
| 517 | `ShowTutorialWindow` | `void` | int nWindow |
| 518 | `StartCreditSequence` | `void` | int bTransparentBackground |
| 519 | `IsCreditSequenceInProgress` | `int` | — |
| 520 | `SWMG_SetLateralAccelerationPerSecond` | `void` | float fLAPS |
| 521 | `SWMG_GetLateralAccelerationPerSecond` | `float` | — |
| 522 | `GetCurrentAction` | `int` | object oObject=OBJECT_SELF |
| 523 | `GetDifficultyModifier` | `float` | — |
| 524 | `GetAppearanceType` | `int` | object oCreature |
| 525 | `FloatingTextStrRefOnCreature` | `void` | int nStrRefToDisplay, object oCreatureToFloatAbove, int bBroadcastToFaction=TRUE |
| 526 | `FloatingTextStringOnCreature` | `void` | string sStringToDisplay, object oCreatureToFloatAbove, int bBroadcastToFaction=TRUE |
| 527 | `GetTrapDisarmable` | `int` | object oTrapObject |
| 528 | `GetTrapDetectable` | `int` | object oTrapObject |
| 529 | `GetTrapDetectedBy` | `int` | object oTrapObject, object oCreature |
| 530 | `GetTrapFlagged` | `int` | object oTrapObject |
| 531 | `GetTrapBaseType` | `int` | object oTrapObject |
| 532 | `GetTrapOneShot` | `int` | object oTrapObject |
| 533 | `GetTrapCreator` | `object` | object oTrapObject |
| 534 | `GetTrapKeyTag` | `string` | object oTrapObject |
| 535 | `GetTrapDisarmDC` | `int` | object oTrapObject |
| 536 | `GetTrapDetectDC` | `int` | object oTrapObject |
| 537 | `GetLockKeyRequired` | `int` | object oObject |
| 538 | `GetLockKeyTag` | `int` | object oObject |
| 539 | `GetLockLockable` | `int` | object oObject |
| 540 | `GetLockUnlockDC` | `int` | object oObject |
| 541 | `GetLockLockDC` | `int` | object oObject |
| 542 | `GetPCLevellingUp` | `object` | — |
| 543 | `GetHasFeatEffect` | `int` | int nFeat, object oObject=OBJECT_SELF |
| 544 | `SetPlaceableIllumination` | `void` | object oPlaceable=OBJECT_SELF, int bIlluminate=TRUE |
| 545 | `GetPlaceableIllumination` | `int` | object oPlaceable=OBJECT_SELF |
| 546 | `GetIsPlaceableObjectActionPossible` | `int` | object oPlaceable, int nPlaceableAction |
| 547 | `DoPlaceableObjectAction` | `void` | object oPlaceable, int nPlaceableAction |
| 548 | `GetFirstPC` | `object` | — |
| 549 | `GetNextPC` | `object` | — |
| 550 | `SetTrapDetectedBy` | `int` | object oTrap, object oDetector |
| 551 | `GetIsTrapped` | `int` | object oObject |
| 552 | `SetEffectIcon` | `effect` | effect eEffect, int nIcon |
| 553 | `FaceObjectAwayFromObject` | `void` | object oFacer, object oObjectToFaceAwayFrom |
| 554 | `PopUpDeathGUIPanel` | `void` | object oPC, int bRespawnButtonEnabled=TRUE, int bWaitForHelpButtonEnabled=TRUE, int nHelpStringReference=0, string sHelpString="" |
| 555 | `SetTrapDisabled` | `void` | object oTrap |
| 556 | `GetLastHostileActor` | `object` | object oVictim=OBJECT_SELF |
| 557 | `ExportAllCharacters` | `void` | — |
| 558 | `MusicBackgroundGetDayTrack` | `int` | object oArea |
| 559 | `MusicBackgroundGetNightTrack` | `int` | object oArea |
| 560 | `WriteTimestampedLogEntry` | `void` | string sLogEntry |
| 561 | `GetModuleName` | `string` | — |
| 562 | `GetFactionLeader` | `object` | object oMemberOfFaction |
| 563 | `SWMG_SetSpeedBlurEffect` | `void` | int bEnabled, float fRatio=0.75f |
| 564 | `EndGame` | `void` | int nShowEndGameGui=TRUE |
| 565 | `GetRunScriptVar` | `int` | — |
| 566 | `GetCreatureMovmentType` | `int` | object oidCreature |
| 567 | `AmbientSoundSetDayVolume` | `void` | object oArea, int nVolume |
| 568 | `AmbientSoundSetNightVolume` | `void` | object oArea, int nVolume |
| 569 | `MusicBackgroundGetBattleTrack` | `int` | object oArea |
| 570 | `GetHasInventory` | `int` | object oObject |
| 571 | `GetStrRefSoundDuration` | `float` | int nStrRef |
| 572 | `AddToParty` | `void` | object oPC, object oPartyLeader |
| 573 | `RemoveFromParty` | `void` | object oPC |
| 574 | `AddPartyMember` | `int` | int nNPC, object oCreature |
| 575 | `RemovePartyMember` | `int` | int nNPC |
| 576 | `IsObjectPartyMember` | `int` | object oCreature |
| 577 | `GetPartyMemberByIndex` | `object` | int nIndex |
| 578 | `GetGlobalBoolean` | `int` | string sIdentifier |
| 579 | `SetGlobalBoolean` | `void` | string sIdentifier, int nValue |
| 580 | `GetGlobalNumber` | `int` | string sIdentifier |
| 581 | `SetGlobalNumber` | `void` | string sIdentifier, int nValue |
| 582 | `AurPostString` | `void` | string sString, int nX, int nY, float fLife |
| 583 | `SWMG_GetLastEvent` | `string` | — |
| 584 | `SWMG_GetLastEventModelName` | `string` | — |
| 585 | `SWMG_GetObjectByName` | `object` | string sName |
| 586 | `SWMG_PlayAnimation` | `void` | object oObject, string sAnimName, int bLooping=1, int bQueue=0, int bOverlay=0 |
| 587 | `SWMG_GetLastBulletHitDamage` | `int` | — |
| 588 | `SWMG_GetLastBulletHitTarget` | `int` | — |
| 589 | `SWMG_GetLastBulletHitShooter` | `object` | — |
| 590 | `SWMG_AdjustFollowerHitPoints` | `int` | object oFollower, int nHP, int nAbsolute=0 |
| 591 | `SWMG_OnBulletHit` | `void` | — |
| 592 | `SWMG_OnObstacleHit` | `void` | — |
| 593 | `SWMG_GetLastFollowerHit` | `object` | — |
| 594 | `SWMG_GetLastObstacleHit` | `object` | — |
| 595 | `SWMG_GetLastBulletFiredDamage` | `int` | — |
| 596 | `SWMG_GetLastBulletFiredTarget` | `int` | — |
| 597 | `SWMG_GetObjectName` | `string` | object oid=OBJECT_SELF |
| 598 | `SWMG_OnDeath` | `void` | — |
| 599 | `SWMG_IsFollower` | `int` | object oid=OBJECT_SELF |
| 600 | `SWMG_IsPlayer` | `int` | object oid=OBJECT_SELF |
| 601 | `SWMG_IsEnemy` | `int` | object oid=OBJECT_SELF |
| 602 | `SWMG_IsTrigger` | `int` | object oid=OBJECT_SELF |
| 603 | `SWMG_IsObstacle` | `int` | object oid=OBJECT_SELF |
| 604 | `SWMG_SetFollowerHitPoints` | `void` | object oFollower, int nHP |
| 605 | `SWMG_OnDamage` | `void` | — |
| 606 | `SWMG_GetLastHPChange` | `int` | — |
| 607 | `SWMG_RemoveAnimation` | `void` | object oObject, string sAnimName |
| 608 | `SWMG_GetCameraNearClip` | `float` | — |
| 609 | `SWMG_GetCameraFarClip` | `float` | — |
| 610 | `SWMG_SetCameraClip` | `void` | float fNear, float fFar |
| 611 | `SWMG_GetPlayer` | `object` | — |
| 612 | `SWMG_GetEnemyCount` | `int` | — |
| 613 | `SWMG_GetEnemy` | `object` | int nEntry |
| 614 | `SWMG_GetObstacleCount` | `int` | — |
| 615 | `SWMG_GetObstacle` | `object` | int nEntry |
| 616 | `SWMG_GetHitPoints` | `int` | object oFollower |
| 617 | `SWMG_GetMaxHitPoints` | `int` | object oFollower |
| 618 | `SWMG_SetMaxHitPoints` | `void` | object oFollower, int nMaxHP |
| 619 | `SWMG_GetSphereRadius` | `float` | object oFollower |
| 620 | `SWMG_SetSphereRadius` | `void` | object oFollower, float fRadius |
| 621 | `SWMG_GetNumLoops` | `int` | object oFollower |
| 622 | `SWMG_SetNumLoops` | `void` | object oFollower, int nNumLoops |
| 623 | `SWMG_GetPosition` | `vector` | object oFollower |
| 624 | `SWMG_GetGunBankCount` | `int` | object oFollower |
| 625 | `SWMG_GetGunBankBulletModel` | `string` | object oFollower, int nGunBank |
| 626 | `SWMG_GetGunBankGunModel` | `string` | object oFollower, int nGunBank |
| 627 | `SWMG_GetGunBankDamage` | `int` | object oFollower, int nGunBank |
| 628 | `SWMG_GetGunBankTimeBetweenShots` | `float` | object oFollower, int nGunBank |
| 629 | `SWMG_GetGunBankLifespan` | `float` | object oFollower, int nGunBank |
| 630 | `SWMG_GetGunBankSpeed` | `float` | object oFollower, int nGunBank |
| 631 | `SWMG_GetGunBankTarget` | `int` | object oFollower, int nGunBank |
| 632 | `SWMG_SetGunBankBulletModel` | `void` | object oFollower, int nGunBank, string sBulletModel |
| 633 | `SWMG_SetGunBankGunModel` | `void` | object oFollower, int nGunBank, string sGunModel |
| 634 | `SWMG_SetGunBankDamage` | `void` | object oFollower, int nGunBank, int nDamage |
| 635 | `SWMG_SetGunBankTimeBetweenShots` | `void` | object oFollower, int nGunBank, float fTBS |
| 636 | `SWMG_SetGunBankLifespan` | `void` | object oFollower, int nGunBank, float fLifespan |
| 637 | `SWMG_SetGunBankSpeed` | `void` | object oFollower, int nGunBank, float fSpeed |
| 638 | `SWMG_SetGunBankTarget` | `void` | object oFollower, int nGunBank, int nTarget |
| 639 | `SWMG_GetLastBulletHitPart` | `string` | — |
| 640 | `SWMG_IsGunBankTargetting` | `int` | object oFollower, int nGunBank |
| 641 | `SWMG_GetPlayerOffset` | `vector` | — |
| 642 | `SWMG_GetPlayerInvincibility` | `float` | — |
| 643 | `SWMG_GetPlayerSpeed` | `float` | — |
| 644 | `SWMG_GetPlayerMinSpeed` | `float` | — |
| 645 | `SWMG_GetPlayerAccelerationPerSecond` | `float` | — |
| 646 | `SWMG_GetPlayerTunnelPos` | `vector` | — |
| 647 | `SWMG_SetPlayerOffset` | `void` | vector vOffset |
| 648 | `SWMG_SetPlayerInvincibility` | `void` | float fInvincibility |
| 649 | `SWMG_SetPlayerSpeed` | `void` | float fSpeed |
| 650 | `SWMG_SetPlayerMinSpeed` | `void` | float fMinSpeed |
| 651 | `SWMG_SetPlayerAccelerationPerSecond` | `void` | float fAPS |
| 652 | `SWMG_SetPlayerTunnelPos` | `void` | vector vTunnel |
| 653 | `SWMG_GetPlayerTunnelNeg` | `vector` | — |
| 654 | `SWMG_SetPlayerTunnelNeg` | `void` | vector vTunnel |
| 655 | `SWMG_GetPlayerOrigin` | `vector` | — |
| 656 | `SWMG_SetPlayerOrigin` | `void` | vector vOrigin |
| 657 | `SWMG_GetGunBankHorizontalSpread` | `float` | object oEnemy, int nGunBank |
| 658 | `SWMG_GetGunBankVerticalSpread` | `float` | object oEnemy, int nGunBank |
| 659 | `SWMG_GetGunBankSensingRadius` | `float` | object oEnemy, int nGunBank |
| 660 | `SWMG_GetGunBankInaccuracy` | `float` | object oEnemy, int nGunBank |
| 661 | `SWMG_SetGunBankHorizontalSpread` | `void` | object oEnemy, int nGunBank, float fHorizontalSpread |
| 662 | `SWMG_SetGunBankVerticalSpread` | `void` | object oEnemy, int nGunBank, float fVerticalSpread |
| 663 | `SWMG_SetGunBankSensingRadius` | `void` | object oEnemy, int nGunBank, float fSensingRadius |
| 664 | `SWMG_SetGunBankInaccuracy` | `void` | object oEnemy, int nGunBank, float fInaccuracy |
| 665 | `SWMG_GetIsInvulnerable` | `int` | object oFollower |
| 666 | `SWMG_StartInvulnerability` | `void` | object oFollower |
| 667 | `SWMG_GetPlayerMaxSpeed` | `float` | — |
| 668 | `SWMG_SetPlayerMaxSpeed` | `void` | float fMaxSpeed |
| 669 | `AddJournalWorldEntry` | `void` | int nIndex, string szEntry, string szTitle="World Entry" |
| 670 | `AddJournalWorldEntryStrref` | `void` | int strref, int strrefTitle |
| 671 | `BarkString` | `void` | object oCreature, int strRef, int nBarkX=-1, int nBarkY=-1 |
| 672 | `DeleteJournalWorldAllEntries` | `void` | — |
| 673 | `DeleteJournalWorldEntry` | `void` | int nIndex |
| 674 | `DeleteJournalWorldEntryStrref` | `void` | int strref |
| 675 | `EffectForceDrain` | `effect` | int nDamage |
| 676 | `EffectPsychicStatic` | `effect` | — |
| 677 | `PlayVisualAreaEffect` | `void` | int nEffectID, location lTarget |
| 678 | `SetJournalQuestEntryPicture` | `void` | string szPlotID, object oObject, int nPictureIndex, int bAllPartyMemebers=TRUE, int bAllPlayers=FALSE |
| 679 | `GetLocalBoolean` | `int` | object oObject, int nIndex |
| 680 | `SetLocalBoolean` | `void` | object oObject, int nIndex, int nValue |
| 681 | `GetLocalNumber` | `int` | object oObject, int nIndex |
| 682 | `SetLocalNumber` | `void` | object oObject, int nIndex, int nValue |
| 683 | `SWMG_GetSoundFrequency` | `int` | object oFollower, int nSound |
| 684 | `SWMG_SetSoundFrequency` | `void` | object oFollower, int nSound, int nFrequency |
| 685 | `SWMG_GetSoundFrequencyIsRandom` | `int` | object oFollower, int nSound |
| 686 | `SWMG_SetSoundFrequencyIsRandom` | `void` | object oFollower, int nSound, int bIsRandom |
| 687 | `SWMG_GetSoundVolume` | `int` | object oFollower, int nSound |
| 688 | `SWMG_SetSoundVolume` | `void` | object oFollower, int nSound, int nVolume |
| 689 | `SoundObjectGetPitchVariance` | `float` | object oSound |
| 690 | `SoundObjectSetPitchVariance` | `void` | object oSound, float fVariance |
| 691 | `SoundObjectGetVolume` | `int` | object oSound |
| 692 | `GetGlobalLocation` | `location` | string sIdentifier |
| 693 | `SetGlobalLocation` | `void` | string sIdentifier, location lValue |
| 694 | `AddAvailableNPCByObject` | `int` | int nNPC, object oCreature |
| 695 | `RemoveAvailableNPC` | `int` | int nNPC |
| 696 | `IsAvailableCreature` | `int` | int nNPC |
| 697 | `AddAvailableNPCByTemplate` | `int` | int nNPC, string sTemplate |
| 698 | `SpawnAvailableNPC` | `object` | int nNPC, location lPosition |
| 699 | `IsNPCPartyMember` | `int` | int nNPC |
| 700 | `ActionBarkString` | `void` | int strRef |
| 701 | `GetIsConversationActive` | `int` | — |
| 702 | `EffectLightsaberThrow` | `effect` | object oTarget1, object oTarget2=OBJECT_INVALID, object oTarget3=OBJECT_INVALID, int nAdvancedDamage=0 |
| 703 | `EffectWhirlWind` | `effect` | — |
| 704 | `GetPartyAIStyle` | `int` | — |
| 705 | `GetNPCAIStyle` | `int` | object oCreature |
| 706 | `SetPartyAIStyle` | `void` | int nStyle |
| 707 | `SetNPCAIStyle` | `void` | object oCreature, int nStyle |
| 708 | `SetNPCSelectability` | `void` | int nNPC, int nSelectability |
| 709 | `GetNPCSelectability` | `int` | int nNPC |
| 710 | `ClearAllEffects` | `void` | — |
| 711 | `GetLastConversation` | `string` | — |
| 712 | `ShowPartySelectionGUI` | `void` | string sExitScript="", int nForceNPC1=-1, int nForceNPC2=-1, int nAllowCancel=FALSE |
| 713 | `GetStandardFaction` | `int` | object oObject |
| 714 | `GivePlotXP` | `void` | string sPlotName, int nPercentage |
| 715 | `GetMinOneHP` | `int` | object oObject |
| 716 | `SetMinOneHP` | `void` | object oObject, int nMinOneHP |
| 717 | `SWMG_GetPlayerTunnelInfinite` | `vector` | — |
| 718 | `SWMG_SetPlayerTunnelInfinite` | `void` | vector vInfinite |
| 719 | `SetGlobalFadeIn` | `void` | float fWait=0.0f, float fLength=0.0f, float fR=0.0f, float fG=0.0f, float fB=0.0f |
| 720 | `SetGlobalFadeOut` | `void` | float fWait=0.0f, float fLength=0.0f, float fR=0.0f, float fG=0.0f, float fB=0.0f |
| 721 | `GetLastHostileTarget` | `object` | object oAttacker=OBJECT_SELF |
| 722 | `GetLastAttackAction` | `int` | object oAttacker=OBJECT_SELF |
| 723 | `GetLastForcePowerUsed` | `int` | object oAttacker=OBJECT_SELF |
| 724 | `GetLastCombatFeatUsed` | `int` | object oAttacker=OBJECT_SELF |
| 725 | `GetLastAttackResult` | `int` | object oAttacker=OBJECT_SELF |
| 726 | `GetWasForcePowerSuccessful` | `int` | object oAttacker=OBJECT_SELF |
| 727 | `GetFirstAttacker` | `object` | object oCreature=OBJECT_SELF |
| 728 | `GetNextAttacker` | `object` | object oCreature=OBJECT_SELF |
| 729 | `SetFormation` | `void` | object oAnchor, object oCreature, int nFormationPattern, int nPosition |
| 730 | `ActionFollowLeader` | `void` | — |
| 731 | `SetForcePowerUnsuccessful` | `void` | int nResult, object oCreature=OBJECT_SELF |
| 732 | `GetIsDebilitated` | `int` | object oCreature=OBJECT_SELF |
| 733 | `PlayMovie` | `void` | string sMovie, int nStreamingMusic=FALSE |
| 734 | `SaveNPCState` | `void` | int nNPC |
| 735 | `GetCategoryFromTalent` | `int` | talent tTalent |
| 736 | `SurrenderByFaction` | `void` | int nFactionFrom, int nFactionTo |
| 737 | `ChangeFactionByFaction` | `void` | int nFactionFrom, int nFactionTo |
| 738 | `PlayRoomAnimation` | `void` | string sRoom, int nAnimation |
| 739 | `ShowGalaxyMap` | `void` | int nPlanet |
| 740 | `SetPlanetSelectable` | `void` | int nPlanet, int bSelectable |
| 741 | `GetPlanetSelectable` | `int` | int nPlanet |
| 742 | `SetPlanetAvailable` | `void` | int nPlanet, int bAvailable |
| 743 | `GetPlanetAvailable` | `int` | int nPlanet |
| 744 | `GetSelectedPlanet` | `int` | — |
| 745 | `SoundObjectFadeAndStop` | `void` | object oSound, float fSeconds |
| 746 | `SetAreaFogColor` | `void` | object oArea, float fRed, float fGreen, float fBlue |
| 747 | `ChangeItemCost` | `void` | string sItem, float fCostMultiplier |
| 748 | `GetIsLiveContentAvailable` | `int` | int nPkg |
| 749 | `ResetDialogState` | `void` | — |
| 750 | `SetGoodEvilValue` | `void` | object oCreature, int nAlignment |
| 751 | `GetIsPoisoned` | `int` | object oObject |
| 752 | `GetSpellTarget` | `object` | object oCreature=OBJECT_SELF |
| 753 | `SetSoloMode` | `void` | int bActivate |
| 754 | `EffectCutSceneHorrified` | `effect` | — |
| 755 | `EffectCutSceneParalyze` | `effect` | — |
| 756 | `EffectCutSceneStunned` | `effect` | — |
| 757 | `CancelPostDialogCharacterSwitch` | `void` | — |
| 758 | `SetMaxHitPoints` | `void` | object oObject, int nMaxHP |
| 759 | `NoClicksFor` | `void` | float fDuration |
| 760 | `HoldWorldFadeInForDialog` | `void` | — |
| 761 | `ShipBuild` | `int` | — |
| 762 | `SurrenderRetainBuffs` | `void` | — |
| 763 | `SuppressStatusSummaryEntry` | `void` | int nNumEntries=1 |
| 764 | `GetCheatCode` | `int` | int nCode |
| 765 | `SetMusicVolume` | `void` | float fVolume=1.0f |
| 766 | `CreateItemOnFloor` | `object` | string sTemplate, location lLocation, int bUseAppearAnimation=FALSE |
| 767 | `SetAvailableNPCId` | `void` | INT nNPC, OBJECT_ID oidNPC |
| 768 | `GetScriptParameter` | `int` | int nIndex |
| 769 | `SetFadeUntilScript` | `void` | — |
| 770 | `EffectForceBody` | `effect` | int nLevel |
| 771 | `GetItemComponent` | `int` | — |
| 772 | `GetItemComponentPieceValue` | `int` | — |
| 773 | `ShowChemicalUpgradeScreen` | `void` | object oCharacter |
| 774 | `GetChemicals` | `int` | — |
| 775 | `GetChemicalPieceValue` | `int` | — |
| 776 | `GetSpellForcePointCost` | `int` | — |
| 777 | `EffectFury` | `effect` | — |
| 778 | `EffectBlind` | `effect` | — |
| 779 | `EffectFPRegenModifier` | `effect` | int nPercent |
| 780 | `EffectVPRegenModifier` | `effect` | int nPercent |
| 781 | `EffectCrush` | `effect` | — |
| 782 | `SWMG_GetSwoopUpgrade` | `int` | int nSlot |
| 783 | `GetFeatAcquired` | `int` | int nFeat, object oCreature=OBJECT_SELF |
| 784 | `GetSpellAcquired` | `int` | int nSpell, object oCreature=OBJECT_SELF |
| 785 | `ShowSwoopUpgradeScreen` | `void` | — |
| 786 | `GrantFeat` | `void` | int nFeat, object oCreature |
| 787 | `GrantSpell` | `void` | int nSpell, object oCreature |
| 788 | `SpawnMine` | `void` | int nMineType, location lPoint, int nDetectDCBase, int nDisarmDCBase, object oCreator |
| 789 | `SWMG_GetTrackPosition` | `vector` | object oFollower |
| 790 | `SWMG_SetFollowerPosition` | `vector` | vector vPos |
| 791 | `SetFakeCombatState` | `void` | object oObject, int nEnable |
| 792 | `SWMG_DestroyMiniGameObject` | `void` | object oObject |
| 793 | `GetOwnerDemolitionsSkill` | `int` | object oObject |
| 794 | `SetOrientOnClick` | `void` | object oCreature=OBJECT_SELF, int nState=TRUE |
| 795 | `GetInfluence` | `int` | int nNPC |
| 796 | `SetInfluence` | `void` | int nNPC, int nInfluence |
| 797 | `ModifyInfluence` | `void` | int nNPC, int nModifier |
| 798 | `GetRacialSubType` | `int` | object oTarget |
| 799 | `IncrementGlobalNumber` | `void` | string sIdentifier, int nAmount |
| 800 | `DecrementGlobalNumber` | `void` | string sIdentifier, int nAmount |
| 801 | `SetBonusForcePoints` | `void` | object oCreature, int nBonusFP |
| 802 | `AddBonusForcePoints` | `void` | object oCreature, int nBonusFP |
| 803 | `GetBonusForcePoints` | `void` | object oCreature |
| 804 | `SWMG_SetJumpSpeed` | `void` | float fSpeed |
| 805 | `IsMoviePlaying` | `int` | — |
| 806 | `QueueMovie` | `None` | — |
| 807 | `PlayMovieQueue` | `None` | — |
| 808 | `YavinHackDoorClose` | `None` | — |
| 809 | `EffectDroidConfused` | `None` | — |
| 810 | `IsStealthed` | `None` | — |
| 811 | `IsMeditating` | `None` | — |
| 812 | `IsInTotalDefense` | `None` | — |
| 813 | `SetHealTarget` | `None` | — |
| 814 | `GetHealTarget` | `None` | — |
| 815 | `GetRandomDestination` | `None` | — |
| 816 | `IsFormActive` | `None` | — |
| 817 | `GetSpellFormMask` | `None` | — |
| 818 | `GetSpellBaseForcePointCost` | `None` | — |
| 819 | `SetKeepStealthInDialog` | `None` | — |
| 820 | `HasLineOfSight` | `None` | — |
| 821 | `ShowDemoScreen` | `None` | — |
| 822 | `ForceHeartbeat` | `None` | — |
| 823 | `EffectForceSight` | `None` | — |
| 824 | `IsRunning` | `None` | — |
| 825 | `SWMG_PlayerApplyForce` | `None` | — |
| 826 | `SetForfeitConditions` | `None` | — |
| 827 | `GetLastForfeitViolation` | `None` | — |
| 828 | `ModifyReflexSavingThrowBase` | `None` | — |
| 829 | `ModifyFortitudeSavingThrowBase` | `None` | — |
| 830 | `ModifyWillSavingThrowBase` | `None` | — |
| 831 | `GetScriptStringParameter` | `None` | — |
| 832 | `GetObjectPersonalSpace` | `None` | — |
| 833 | `AdjustCreatureAttributes` | `None` | — |
| 834 | `SetCreatureAILevel` | `None` | — |
| 835 | `ResetCreatureAILevel` | `None` | — |
| 836 | `AddAvailablePUPByTemplate` | `None` | — |
| 837 | `AddAvailablePUPByObject` | `None` | — |
| 838 | `AssignPUP` | `None` | — |
| 839 | `SpawnAvailablePUP` | `None` | — |
| 840 | `AddPartyPuppet` | `None` | — |
| 841 | `GetPUPOwner` | `None` | — |
| 842 | `GetIsPuppet` | `None` | — |
| 843 | `ActionFollowOwner` | `None` | — |
| 844 | `GetIsPartyLeader` | `None` | — |
| 845 | `GetPartyLeader` | `None` | — |
| 846 | `RemoveNPCFromPartyToBase` | `None` | — |
| 847 | `CreatureFlourishWeapon` | `None` | — |
| 848 | `EffectMindTrick` | `None` | — |
| 849 | `EffectFactionModifier` | `None` | — |
| 850 | `ChangeObjectAppearance` | `None` | — |
| 851 | `GetIsXBox` | `None` | — |
| 852 | `EffectDroidScramble` | `None` | — |
| 853 | `ActionSwitchWeapons` | `None` | — |
| 854 | `PlayOverlayAnimation` | `None` | — |
| 855 | `UnlockAllSongs` | `None` | — |
| 856 | `DisableMap` | `None` | — |
| 857 | `DetonateMine` | `None` | — |
| 858 | `DisableHealthRegen` | `None` | — |
| 859 | `SetCurrentForm` | `None` | — |
| 860 | `SetDisableTransit` | `None` | — |
| 861 | `SetInputClass` | `None` | — |
| 862 | `SetForceAlwaysUpdate` | `None` | — |
| 863 | `EnableRain` | `None` | — |
| 864 | `DisplayMessageBox` | `None` | — |
| 865 | `DisplayDatapad` | `None` | — |
| 866 | `RemoveHeartbeat` | `None` | — |
| 867 | `RemoveEffectByID` | `None` | — |
| 868 | `RemoveEffectByExactMatch` | `None` | — |
| 869 | `AdjustCreatureSkills` | `None` | — |
| 870 | `GetSkillRankBase` | `None` | — |
| 871 | `EnableRendering` | `None` | — |
| 872 | `GetCombatActionsPending` | `None` | — |
| 873 | `SaveNPCByObject` | `None` | — |
| 874 | `SavePUPByObject` | `None` | — |
| 875 | `GetIsPlayerMadeCharacter` | `None` | — |
| 876 | `RebuildPartyTable` | `None` | — |
