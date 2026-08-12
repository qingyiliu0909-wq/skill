---
name: "nav-pathfinding"
description: "EM game navigation and pathfinding system guide. Invoke when modifying navmesh, async pathfinding, PathFollowingComponent, NavQuery thread safety, culling, or tile loading logic."
---

# EM Navigation & Pathfinding System Guide

## Engine Source Path

Project uses a customized UE 4.27 engine (repo: `http://10.18.200.6:8888/engineteam/unrealengine`). Engine source path varies per developer machine.

### Auto-Detect Engine Path

Before referencing engine source, run the detection script (caches result in `.engine_path`):
```powershell
# From skill directory: .trae/skills/nav-pathfinding/
.\detect_engine_path.bat
```

Detection logic:
1. Check cached `.engine_path` file — if valid, use it directly (no re-detection)
2. Read `EngineAssociation` GUID from project's `EM.uproject`
3. Look up Windows registry `HKCU:\Software\Epic Games\Unreal Engine\Builds\{GUID}`
4. Cache result to `.engine_path` for future use

If auto-detection fails, manually set the path:
```powershell
echo "C:\Your\Engine\Path\unrealengine" > .trae/skills/nav-pathfinding/.engine_path
```

**Note**: `.engine_path` is a local cache file and should NOT be committed to version control (SVN). Add it to svn:ignore.

### Engine Source Structure

Once engine path is resolved (referred to as `<ENGINE_ROOT>` below), key source locations:

| Module | Path | Key Files |
|--------|------|-----------|
| NavigationSystem | `<ENGINE_ROOT>/Engine/Source/Runtime/NavigationSystem/` | NavigationData.h/.cpp, NavigationSystem.h/.cpp, NavigationPath.h/.cpp, RecastNavMesh.h/.cpp, PImplRecastNavMesh.h/.cpp |
| AIModule | `<ENGINE_ROOT>/Engine/Source/Runtime/AIModule/` | PathFollowingComponent.h/.cpp, AIController.h/.cpp |
| NavMesh | `<ENGINE_ROOT>/Engine/Source/Runtime/NavigationSystem/Public/NavMesh/` | PImplRecastNavMesh.h, RecastNavMesh.h, NavMeshPath.h, RecastHelpers.h |
| NavMesh Private | `<ENGINE_ROOT>/Engine/Source/Runtime/NavigationSystem/Private/NavMesh/` | PImplRecastNavMesh.cpp, RecastNavMesh.cpp, NavMeshPath.cpp |

## Project Key Files

| File | Purpose |
|------|---------|
| `Source/EM/Public/AI/EMRecastNavMesh.h` | Custom RecastNavMesh with culling, async pathfinding, framed tile loading |
| `Source/EM/Private/AI/EMRecastNavMesh.cpp` | Core implementation: EMFindPath, culling, tile attach, nav query thread isolation |
| `Source/EM/Public/AI/Settings/EMNavigateSettings.h` | Navigation config: bUseAsyncFindPath, MaxRequestsLevel, culling toggles |
| `Source/EM/Private/AI/Settings/EMNavigateSettings.cpp` | Default settings initialization |
| `Source/EM/Public/Common/NavigationFunctionLibrary.h` | Runtime nav APIs: ImmediateRepath, ProjectPoint, TestPathExists |
| `Source/EM/Private/Common/NavigationFunctionLibrary.cpp` | Runtime nav API implementations |
| `Source/EM/Public/Char/MonsterPathFollowingComponent.h` | Custom PathFollowingComponent for monsters |
| `Source/EM/Private/Char/MonsterPathFollowingComponent.cpp` | Path following: RequestMove, UpdatePathSegment, OnPathFinished, HandlePathUpdateEvent |
| `Source/EM/Private/AI/MonMoveProcessComponent.cpp` | Move request stack: PushMoveRequest, CrossLevelCheck |
| `Source/EM/Private/AI/MonsterAIController.cpp` | AI controller: ShouldPostponePathUpdates (returns false), move initiation |
| `Source/EMEditor/Public/Common/WCEditFunctionLibrary.h` | Editor nav tools: culling, rebuild, export |
| `Source/EMEditor/Private/Common/WCEditFunctionLibrary.cpp` | Editor nav tool implementations |

## Architecture Overview

### Pathfinding Request Flow

Two independent request paths exist:

**Path A: Initial MoveTo (Synchronous)**
```
MonMoveProcessComponent::PushMoveRequest()
  → AAIController::MoveTo()
    → BuildPathfindingQuery()
    → FindPathForMoveRequest() → NavSys->FindPathSync(Query)
    → PathFollowingComponent::RequestMove(MoveRequest, Path)
```

**Path B: Path Recalculation (Async when bUseAsyncFindPath=true)**
```
ANavigationData::TickActor()
  → Observe path changes (ObservedPaths)
    → Generate RepathRequests
      → if bUseAsyncFindPath: NavSys->FindPathAsync()
      → else: FindPath() (synchronous)
```

### Async Pathfinding Pipeline

```
Game Thread Tick:
  1. Swap() completed results from last frame
  2. TriggerAsyncQueries() → FSimpleDelegateGraphTask dispatches to worker thread
  3. DispatchAsyncQueriesResults() for last frame's results

Worker Thread (PerformAsyncQueries):
  1. Loop through queries
  2. NavData->FindPath() → EMFindPath()
  3. Check bAbortAsyncQueriesRequested (TAtomic<bool>) per iteration
  4. Append results to AsyncPathFindingCompletedQueries / AsyncPathFindingResults

Next Frame Game Thread:
  DispatchAsyncQueriesResults() → OnDoneDelegate → OnAsyncFindPathDone()
    → FNavigationPath::DoneUpdating() → ObserverDelegate.Broadcast()
    → PathFollowingComponent::OnPathEvent() → HandlePathUpdateEvent()
```

### EMFindPath bUseAsyncFindPath Branch

When `bUseAsyncFindPath = true`, EMFindPath creates a temporary FNavMeshPath:
```cpp
FNavPathSharedPtr SharedPath = MakeShareable(new FNavMeshPath());
// ... perform Detour pathfinding on this temp object
Result.Path = SharedPath;
```

This temp object is later MoveTemp'd into the final path instance in DispatchAsyncQueriesResults, avoiding worker thread directly writing to PathFollowingComponent's shared path.

When `bUseAsyncFindPath = false`, EMFindPath reuses Query.PathInstanceToFill or creates via CreatePathInstance.

### Callback Chain

```
OnAsyncFindPathDone()
  → FNavigationPath::DoneUpdating(ENavPathUpdateType::GoalMoved)
    → ObserverDelegate.Broadcast(this, ENavPathEvent::UpdatedDueToGoalMoved)
      → UPathFollowingComponent::OnPathEvent()
        → HandlePathUpdateEvent()
          → OnPathUpdated()
          → SetMoveSegment(CurrentSegment)
            → FollowPathSegment(DeltaTime)
```

## Thread Safety Mechanisms

### 1. NavQuery Thread Isolation (CRITICAL)

Macro `EMINITIALIZE_NAVQUERY` / Engine `INITIALIZE_NAVQUERY`:
```cpp
dtNavMeshQuery NavQueryVariable##Private;
dtNavMeshQuery& NavQueryVariable = IsInGameThread()
    ? RecastImpl->SharedNavQuery
    : NavQueryVariable##Private;
NavQueryVariable.init(RecastImpl->DetourNavMesh, NumNodes, &LinkFilter);
```

- **Game thread**: Uses `SharedNavQuery` (FPImplRecastNavMesh member) — safe because game thread is serial
- **Worker thread**: Uses stack-local `NavQueryVariable##Private` — fully isolated per thread

This pattern is used in ALL Detour query functions: FindPath, FindNearestPoly, ProjectPointToNavigation, TestPathExists, etc.

### 2. Swap + Deferred Dispatch

```cpp
// UNavigationSystemV1::Tick
TArray<FAsyncPathFindingQuery> AsyncPathFindingCompletedQueriesToDispatch;
Swap(AsyncPathFindingCompletedQueriesToDispatch, AsyncPathFindingCompletedQueries);
```

Swap is O(1) pointer swap. After swap:
- Game thread owns `ToDispatch` copy, safely iterates
- Worker thread owns original array, appends new results
- No concurrent access to same array instance

### 3. TAtomic<bool> bAbortAsyncQueriesRequested

Worker thread reads this atomically per query iteration. Game thread sets it via PostponeAsyncQueries() then calls WaitUntilTaskCompletes().

### 4. Temporary Path + MoveTemp Transfer

EMFindPath async branch creates new FNavMeshPath per call. Worker thread writes to temp object. DispatchAsyncQueriesResults uses MoveTemp to transfer data to final path instance on game thread.

### 5. FNavPathSharedPtr Atomic Reference Counting

TSharedPtr reference counting uses atomic operations. Safe for cross-thread holding/releasing.

### 6. NavPathDataLock (EM Addition, Currently Commented Out)

EM added `mutable FCriticalSection NavPathDataLock` to FNavigationPath in engine (`<ENGINE_ROOT>/Engine/Source/Runtime/NavigationSystem/Public/NavigationData.h:378`). Usage commented out in:
- EMRecastNavMesh.cpp:446
- MonsterPathFollowingComponent.cpp:1216

Commented because the temp-path + MoveTemp pattern already avoids direct concurrent writes. Reserved for future fine-grained concurrent access.

### 7. ShouldPostponePathUpdates Override

MonsterAIController overrides to return false. Equivalent protection via NavLinkJumpComponent::PathFindingStage check in PushMoveRequest.

### 8. MaxProcessedRequests Budget

Async mode: MaxProcessedRequests = 1000 (UE default). Sync mode: scaled by platform and EEMUnitBudgetQualityLevel.

## Navigation Mesh Construction & Culling

### Two-Phase Build

1. **First Build**: Standard navmesh generation + isolated polygon culling via NavModifierVolume
2. **Second Build**: Region-based division + additional culling

### Isolated Polygon Culling (bCullIsolatedPolysByNavModifier)

Uses OBB (Oriented Bounding Boxes) from NavModifierVolume to identify and remove unreachable polygons. Controlled by settings:
- bCullIsolatedPolysByNavModifier
- bDisableWCCullPolyInRuntime / bDisableNOWCCullPolyInRuntime

### Region Division (bOnlyFrameAttachTilesWhenRegionDivided)

Divides navmesh into regions by level. Each region's tiles are attached per-frame to avoid frame spikes.

### Framed Tile Loading

AttachTilesTasks queue processed per frame with configurable batch size. Controlled by bEnablePerFrameAttachedTiles.

## Key Configuration (UEMNavigateSettings)

| Setting | Default | Description |
|---------|---------|-------------|
| bUseAsyncFindPath | true | Enable async pathfinding for repath requests |
| ObservedPathsTickInterval | 0.5s | How often observed paths are checked for updates |
| bCullIsolatedPolysByNavModifier | true | Enable isolated polygon culling |
| bOnlyFrameAttachTilesWhenRegionDivided | true | Per-frame tile attachment when regions divided |
| bEnablePerFrameAttachedTiles | true | Enable framed tile loading |
| PCMaxRequestsLevel | per quality | Max sync pathfinding requests per frame (PC) |
| AndroidMaxRequestsLevel | per quality | Max sync pathfinding requests per frame (Android) |
| IOSMaxRequestsLevel | per quality | Max sync pathfinding requests per frame (iOS) |

Note: MaxRequestsLevel only applies when bUseAsyncFindPath = false. When async, MaxProcessedRequests is fixed at 1000.

## Important Notes

1. **Dedicated Server**: bUseAsyncFindPath forced to false on dedicated servers (NM_DedicatedServer check in BeginPlay)
2. **Engine Customization**: NavPathDataLock is an EM addition to engine FNavigationPath. If modifying engine NavigationData.h, preserve this addition.
3. **Worker Thread UObject Access**: Engine acknowledges this is unsafe (@todo comment in PerformAsyncQueries). PostponeAsyncQueries + WaitUntilTaskCompletes is the current safeguard.
4. **DetourNavMesh Read-Write Race**: If game thread modifies navmesh tiles while worker thread queries, DetourNavMesh internal structures can corrupt. PostponeAsyncQueries is called before tile modifications to mitigate.
5. **EMFindPath vs ARecastNavMesh::FindPath**: EM replaces both FindPathImplementation and FindHierarchicalPathImplementation with EMFindPath. The key difference is the bUseAsyncFindPath branch creating temp path objects.
