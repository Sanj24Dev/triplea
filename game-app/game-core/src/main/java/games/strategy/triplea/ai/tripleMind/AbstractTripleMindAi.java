package games.strategy.triplea.ai.tripleMind;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import games.strategy.engine.data.*;
import games.strategy.engine.framework.GameDataManager;
import games.strategy.engine.framework.GameDataUtils;
import games.strategy.triplea.Properties;
import games.strategy.triplea.ai.AbstractAi;
import games.strategy.triplea.ai.tripleMind.data.*;
import games.strategy.triplea.ai.tripleMind.logging.ProLogUi;
import games.strategy.triplea.ai.tripleMind.logging.ProLogger;
import games.strategy.triplea.ai.tripleMind.util.*;
import games.strategy.triplea.attachments.PoliticalActionAttachment;
import games.strategy.triplea.delegate.DiceRoll;
import games.strategy.triplea.delegate.Matches;
import games.strategy.triplea.delegate.battle.BattleDelegate;
import games.strategy.triplea.delegate.battle.IBattle;
import games.strategy.triplea.delegate.battle.IBattle.BattleType;
import games.strategy.triplea.delegate.data.CasualtyDetails;
import games.strategy.triplea.delegate.data.CasualtyList;
import games.strategy.triplea.delegate.data.PlaceableUnits;
import games.strategy.triplea.delegate.remote.IAbstractPlaceDelegate;
import games.strategy.triplea.delegate.remote.IMoveDelegate;
import games.strategy.triplea.delegate.remote.IPurchaseDelegate;
import games.strategy.triplea.delegate.remote.ITechDelegate;
import games.strategy.triplea.odds.calculator.IBattleCalculator;
import lombok.Getter;
import org.triplea.java.collections.IntegerMap;
import org.triplea.util.Tuple;

import java.lang.reflect.Type;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

import static games.strategy.triplea.ai.tripleMind.ProPurchaseAi.doPlace;
import static games.strategy.triplea.ai.tripleMind.helper.requestMove;
import static games.strategy.triplea.ai.tripleMind.util.ProMoveUtils.doMove;
import static games.strategy.triplea.ai.tripleMind.util.ProPurchaseUtils.getUnitProduction;

/** Pro AI. */
public abstract class AbstractTripleMindAi extends AbstractAi {

  @Getter private final ProOddsCalculator calc;
  @Getter private final ProData proData;

  // Phases
  private final ProCombatMoveAi combatMoveAi;
  private final ProNonCombatMoveAi nonCombatMoveAi;
  private final ProPurchaseAi purchaseAi;
  private final ProRetreatAi retreatAi;
  private final ProScrambleAi scrambleAi;
  private final ProPoliticsAi politicsAi;

  // Data shared across phases
  private Map<Territory, ProTerritory> storedCombatMoveMap;
  private Map<Territory, ProTerritory> storedFactoryMoveMap;
  private Map<Territory, ProPurchaseTerritory> storedPurchaseTerritories;
  private List<PoliticalActionAttachment> storedPoliticalActions;
  private List<Territory> storedStrafingTerritories;

  public AbstractTripleMindAi(
      final String name,
      final IBattleCalculator battleCalculator,
      final ProData proData,
      final String playerLabel) {
    super(name, playerLabel);
    this.proData = proData;
    calc = new ProOddsCalculator(battleCalculator);
    combatMoveAi = new ProCombatMoveAi(this);
    nonCombatMoveAi = new ProNonCombatMoveAi(this);
    purchaseAi = new ProPurchaseAi(this);
    retreatAi = new ProRetreatAi(this);
    scrambleAi = new ProScrambleAi(this);
    politicsAi = new ProPoliticsAi(this);
    storedCombatMoveMap = null;
    storedFactoryMoveMap = null;
    storedPurchaseTerritories = null;
    storedPoliticalActions = null;
    storedStrafingTerritories = new ArrayList<>();
  }

  @Override
  public void stopGame() {
    super.stopGame(); // absolutely MUST call super.stopGame() first
    calc.stop();
  }

  private void initializeData() {
    proData.initialize(this);
  }

  public void setStoredStrafingTerritories(final List<Territory> strafingTerritories) {
    storedStrafingTerritories = strafingTerritories;
  }

  /**
   * Some implementations of {@link IBattleCalculator} do require setting a GameData instance before
   * actually being able to run properly. This method should take care of that.
   */
  protected abstract void prepareData(GameData data);

  @Override
  protected void move(
      final boolean nonCombat,
      final IMoveDelegate moveDel,
      final GameData data,
      final GamePlayer player) {

    String actions = "";
    if (nonCombat)
        actions = requestMove("noncombat");
    else
        actions = requestMove("combat");

    if (actions == null)
        return;

    final Instant start = Instant.now();
    ProLogUi.notifyStartOfRound(data.getSequence().getRound(), player.getName());
    initializeData();
    prepareData(data);
    boolean didCombatMove = false;
    boolean didNonCombatMove = false;

    Gson gson = new Gson();
    Type actionListType = new TypeToken<List<Action>>(){}.getType();
    // skip if null
    List<Action> actionsList = gson.fromJson(actions, actionListType);




    if (nonCombat) {
//      nonCombatMoveAi.doNonCombatMove(storedFactoryMoveMap, storedPurchaseTerritories, moveDel);
//      storedFactoryMoveMap = null;
        for (Action a : actionsList) {
            Map<Territory, ProTerritory> nonCombatMap = new HashMap<>();
            Territory from = data.getMap().getTerritoryOrNull(a.from);
            Territory to = data.getMap().getTerritoryOrNull(a.to);
            Optional<UnitType> unitTypeOpt = data.getUnitTypeList().getUnitType(a.unit);
            if (unitTypeOpt.isEmpty()) {
                System.out.println("Invalid unit type: " + a.unit);
                return;
            }

            UnitType unitType = unitTypeOpt.get();
            assert from != null;
            System.out.println(unitType.toString());
            List<Unit> availableUnits = from.getMatches(Matches.unitIsOfType(unitType));
            if (availableUnits.isEmpty()) {
                System.out.println("No available unit of type " + a.unit + " in " + from.getName());
                return;
            }

            Unit selectedUnit = availableUnits.get(0); // assuming 1 unit per action

            // Get or create ProTerritory for the target
            ProTerritory proTo = nonCombatMap.computeIfAbsent(to, t -> new ProTerritory(t, proData));

            // Add attacking unit from source
            proTo.addUnit(selectedUnit);

            // Store it back
            nonCombatMap.put(to, proTo);
            List<MoveDescription> moves = ProMoveUtils.calculateMoveRoutes(proData, player, nonCombatMap, false);
            doMove(proData, moves, moveDel);
        }

        didNonCombatMove = true;
    } else {
        for (Action a : actionsList) {
            Map<Territory, ProTerritory> attackMap = new HashMap<>();
            Territory from = data.getMap().getTerritoryOrNull(a.from);
            Territory to = data.getMap().getTerritoryOrNull(a.to);
            Optional<UnitType> unitTypeOpt = data.getUnitTypeList().getUnitType(a.unit);
            if (unitTypeOpt.isEmpty()) {
                System.out.println("Invalid unit type: " + a.unit);
                return;
            }

            UnitType unitType = unitTypeOpt.get();
            assert from != null;
            System.out.println(unitType.toString());
            List<Unit> availableUnits = from.getMatches(Matches.unitIsOfType(unitType));
            if (availableUnits.isEmpty()) {
                System.out.println("No available unit of type " + a.unit + " in " + from.getName());
                return;
            }

            Unit selectedUnit = availableUnits.get(0); // assuming 1 unit per action

            // Get or create ProTerritory for the target
            ProTerritory proTo = attackMap.computeIfAbsent(to, t -> new ProTerritory(t, proData));

            // Add attacking unit from source
            proTo.addUnit(selectedUnit);

            // Store it back
            attackMap.put(to, proTo);
            List<MoveDescription> moves = ProMoveUtils.calculateMoveRoutes(proData, player, attackMap, true);
            doMove(proData, moves, moveDel);
        }

        didCombatMove = true;
//        if (storedCombatMoveMap == null) {
//            combatMoveAi.doCombatMove(moveDel);
//        } else {
//            combatMoveAi.doMove(storedCombatMoveMap, moveDel, data, player);
//            storedCombatMoveMap = null;
//        }
//        didCombatMove = true;
//        if (!hasNonCombatMove(getGameStepsForPlayer(data, player, 0))) {
//            nonCombatMoveAi.doNonCombatMove(storedFactoryMoveMap, storedPurchaseTerritories, moveDel);
//            storedFactoryMoveMap = null;
//            didNonCombatMove = true;
//        }
    }



    Duration delta = Duration.between(start, Instant.now());
    ProLogger.info(
        String.format(
            "%s move (didCombatMove=%s  didNonCombatMove=%s) time=%s",
            player.getName(), didCombatMove, didNonCombatMove, delta.toMillis()));
  }

  @Override
  protected void purchase(
      final boolean purchaseForBid,
      final int pusToSpend,
      final IPurchaseDelegate purchaseDelegate,
      final GameData data,
      final GamePlayer player) {


    String actions = requestMove("purchase");
    if (actions == null)
        return;




    final long start = System.currentTimeMillis();
    ProLogUi.notifyStartOfRound(data.getSequence().getRound(), player.getName());
    initializeData();
    if (pusToSpend <= 0) {
      return;
    }
    if (purchaseForBid) {
      prepareData(data);
      storedPurchaseTerritories = purchaseAi.bid(pusToSpend, purchaseDelegate, data);
    } else {
      // Repair factories
      purchaseAi.repair(pusToSpend, purchaseDelegate, data, player);

        final ProPurchaseOptionMap purchaseOptions = proData.getPurchaseOptions();
        Gson gson = new Gson();
        Type actionListType = new TypeToken<List<Action>>(){}.getType();
        List<Action> actionsList = gson.fromJson(actions, actionListType);
        final Map<Territory, ProPurchaseTerritory> purchaseTerritories = new HashMap<>();
        for (Action a : actionsList) {
            Territory t = data.getMap().getTerritoryOrNull(a.to);
            if (t == null) continue;
            if (!purchaseTerritories.containsKey(t)) {
                int unitProd = getUnitProduction(t, player);
                ProPurchaseTerritory ppt = new ProPurchaseTerritory(t, data, player, unitProd);
                purchaseTerritories.put(t, ppt);
            }
            ProPurchaseTerritory ppt = purchaseTerritories.get(t);
            Optional<UnitType> unitType = data.getUnitTypeList().getUnitType(a.unit);
            Unit unit = unitType.get().create(player);
            if (ppt.getCanPlaceTerritories().isEmpty()) {
//                ppt.getCanPlaceTerritories().add(new ProPlaceTerritory(t, data, player));
                ppt.getCanPlaceTerritories().add(new ProPlaceTerritory(t));
            }
            ppt.getCanPlaceTerritories().get(0).getPlaceUnits().add(unit);
        }

        final IntegerMap<ProductionRule> purchaseMap =
                productionRuleMap(purchaseTerritories, purchaseOptions, player);

        // Purchase units
        final String error = purchaseDelegate.purchase(purchaseMap);
        if (error != null) {
            ProLogger.warn("Purchase error: " + error);
        }

    }
    ProLogger.info(player.getName() + " time for purchase=" + (System.currentTimeMillis() - start));
  }

    public IntegerMap<ProductionRule> productionRuleMap(
            final Map<Territory, ProPurchaseTerritory> purchaseTerritories,
            final ProPurchaseOptionMap purchaseOptions, GamePlayer player) {

        ProLogger.info("Populate production rule map");
        final List<Unit> unplacedUnits = player.getMatches(Matches.unitIsNotSea());
        final IntegerMap<ProductionRule> purchaseMap = new IntegerMap<>();
        for (final ProPurchaseOption ppo : purchaseOptions.getAllOptions()) {
            final int numUnits =
                    (int)
                            purchaseTerritories.values().stream()
                                    .map(ProPurchaseTerritory::getCanPlaceTerritories)
                                    .flatMap(Collection::stream)
                                    .map(ProPlaceTerritory::getPlaceUnits)
                                    .flatMap(Collection::stream)
                                    .filter(u -> u.getType().equals(ppo.getUnitType()))
                                    .filter(u -> !unplacedUnits.contains(u))
                                    .count();
            if (numUnits > 0) {
                final int numProductionRule = numUnits / ppo.getQuantity();
                purchaseMap.put(ppo.getProductionRule(), numProductionRule);
                ProLogger.info(numProductionRule + " " + ppo.getProductionRule());
            }
        }
        return purchaseMap;
    }

  private GameData copyData(GameData data) {
    GameDataManager.Options options = GameDataManager.Options.builder().withDelegates(true).build();
    GameData dataCopy = GameDataUtils.cloneGameData(data, options).orElse(null);
    Optional.ofNullable(dataCopy).ifPresent(this::prepareData);
    return dataCopy;
  }

  private static List<GameStep> getGameStepsForPlayer(
      GameData gameData, GamePlayer gamePlayer, int startStep) {
    int stepIndex = 0;
    final List<GameStep> gameSteps = new ArrayList<>();
    for (final GameStep gameStep : gameData.getSequence()) {
      if (stepIndex >= startStep && gamePlayer.equals(gameStep.getPlayerId())) {
        gameSteps.add(gameStep);
      }
      stepIndex++;
    }
    return gameSteps;
  }

  private boolean hasNonCombatMove(Collection<GameStep> steps) {
    return steps.stream().anyMatch(s -> GameStep.isNonCombatMoveStepName(s.getName()));
  }

  @Override
  protected void place(
      final boolean bid,
      final IAbstractPlaceDelegate placeDelegate,
      final GameState data,
      final GamePlayer player) {


    String actions = requestMove("place");
    if (actions == null)
        return;
    final long start = System.currentTimeMillis();
    ProLogUi.notifyStartOfRound(data.getSequence().getRound(), player.getName());
    initializeData();

//      Gson gson = new Gson();
//      Type actionListType = new TypeToken<List<Action>>(){}.getType();
//      List<Action> actionsList = gson.fromJson(actions, actionListType);
//
//        // Create a list to collect all ModelPlacements
//      Map<Territory, List<Unit>> placementsByTerritory = new HashMap<>();
//
//      for (Action a : actionsList) {
//          Territory to = data.getMap().getTerritoryOrNull(a.to);
//          if (to == null) {
//              System.err.println("Invalid placement territory: " + a.to);
//              continue;
//          }
//
//          // Get the unit type
//          UnitType unitType = data.getUnitTypeList().getUnitType(a.unit).orElse(null);
//          if (unitType == null) {
//              System.err.println("Invalid unit type: " + a.unit);
//              continue;
//          }
//
//          Unit newUnit = new Unit(unitType, player, getGameData());
//
//          // Group it under its target territory
//          placementsByTerritory.computeIfAbsent(to, k -> new ArrayList<>()).add(newUnit);
//
//          System.out.println("Placed " + a.unit + " in " + a.to);
//      }
//      for (Map.Entry<Territory, List<Unit>> entry : placementsByTerritory.entrySet()) {
//          Territory territory = entry.getKey();
//          List<Unit> unitsToPlace = entry.getValue();
//
//          // Check if placement is legal
//          PlaceableUnits placeableUnits =
//                  placeDelegate.getPlaceableUnits(unitsToPlace, territory);
//
//          if (placeableUnits.isError()) {
//              System.err.println(
//                      "Cannot place units in " + territory.getName()
//                              + ": " + placeableUnits.getErrorMessage());
//              continue;
//          }
//
//          // Limit to maximum allowed placements
//          int maxAllowed = placeableUnits.getMaxUnits();
//          if (maxAllowed == -1) {
//              maxAllowed = Integer.MAX_VALUE; // No limit
//          }
//
//          int actualCount = Math.min(maxAllowed, unitsToPlace.size());
//          List<Unit> finalUnits = unitsToPlace.subList(0, actualCount);
//
//          // Perform placement
//          doPlace(territory, finalUnits, placeDelegate);
//          System.out.println("Placed in " + territory.getName() + ": " + finalUnits);
//      }


    purchaseAi.place(storedPurchaseTerritories, placeDelegate);
    storedPurchaseTerritories = null;
    ProLogger.info(player.getName() + " time for place=" + (System.currentTimeMillis() - start));
  }

  @Override
  protected void tech(
      final ITechDelegate techDelegate, final GameData data, final GamePlayer player) {
    ProTechAi.tech(techDelegate, data, player);
  }

  public Optional<Territory> retreatQuery(
      final UUID battleId,
      final boolean submerge,
      final Territory battleTerritory,
      final Collection<Territory> possibleTerritories,
      final String message) {
    initializeData();

    // Get battle data
    final GameData data = getGameData();
    final GamePlayer player = this.getGamePlayer();
    final BattleDelegate delegate = data.getBattleDelegate();
    final IBattle battle = delegate.getBattleTracker().getPendingBattle(battleId);

    // If battle is null or amphibious then don't retreat
    if (battle == null || battleTerritory == null || battle.isAmphibious()) {
      return Optional.empty();
    }

    // If attacker with more unit strength or strafing and isn't land battle with only air left then
    // don't retreat
    final boolean isAttacker = player.equals(battle.getAttacker());
    final Collection<Unit> attackers = battle.getAttackingUnits();
    final Collection<Unit> defenders = battle.getDefendingUnits();
    final double strengthDifference =
        ProBattleUtils.estimateStrengthDifference(battleTerritory, attackers, defenders);
    final boolean isStrafing = isAttacker && storedStrafingTerritories.contains(battleTerritory);
    ProLogger.info(
        player.getName()
            + " checking retreat from territory "
            + battleTerritory
            + ", attackers="
            + attackers.size()
            + ", defenders="
            + defenders.size()
            + ", submerge="
            + submerge
            + ", attacker="
            + isAttacker
            + ", isStrafing="
            + isStrafing);
    if ((isStrafing || (isAttacker && strengthDifference > 50))
        && (battleTerritory.isWater() || attackers.stream().anyMatch(Matches.unitIsLand()))) {
      return Optional.empty();
    }
    prepareData(getGameData());
    return retreatAi.retreatQuery(battleId, battleTerritory, possibleTerritories);
  }

  @Override
  public boolean shouldBomberBomb(final Territory territory) {
    return combatMoveAi.isBombing();
  }

  // TODO: Consider supporting this functionality
  @Override
  public Collection<Unit> getNumberOfFightersToMoveToNewCarrier(
      final Collection<Unit> fightersThatCanBeMoved, final Territory from) {
    return new ArrayList<>();
  }

  @Override
  public CasualtyDetails selectCasualties(
      final Collection<Unit> selectFrom,
      final Map<Unit, Collection<Unit>> dependents,
      final int count,
      final String message,
      final DiceRoll dice,
      final GamePlayer hit,
      final Collection<Unit> friendlyUnits,
      final Collection<Unit> enemyUnits,
      final boolean amphibious,
      final Collection<Unit> amphibiousLandAttackers,
      final CasualtyList defaultCasualties,
      final UUID battleId,
      final Territory battleSite,
      final boolean allowMultipleHitsPerUnit) {
    initializeData();

    if (defaultCasualties.size() != count) {
      throw new IllegalStateException(
          String.format(
              "Select Casualties showing different numbers for number of hits to take (%s) vs "
                  + "total size of default casualty selections (%s) in %s (hit = %s)",
              count, defaultCasualties.size(), battleSite, hit.getName()));
    }
    if (defaultCasualties.getKilled().isEmpty()) {
      return new CasualtyDetails(defaultCasualties, false);
    }

    // Consider unit cost
    final CasualtyDetails myCasualties = new CasualtyDetails(false);
    myCasualties.addToDamaged(defaultCasualties.getDamaged());
    final List<Unit> selectFromSorted = new ArrayList<>(selectFrom);
    if (enemyUnits.isEmpty()) {
      selectFromSorted.sort(ProPurchaseUtils.getCostComparator(proData));
    } else {

      // Get battle data
      final GameData data = getGameData();
      final GamePlayer player = this.getGamePlayer();
      final BattleDelegate delegate = data.getBattleDelegate();
      final IBattle battle = delegate.getBattleTracker().getPendingBattle(battleId);

      // If defender and could lose battle then don't consider unit cost as just trying to survive
      boolean needToCheck = true;
      final boolean isAttacker = player.equals(battle.getAttacker());
      if (!isAttacker) {
        final Collection<Unit> attackers = battle.getAttackingUnits();
        final Collection<Unit> defenders = new ArrayList<>(battle.getDefendingUnits());
        defenders.removeAll(defaultCasualties.getKilled());
        final double strengthDifference =
            ProBattleUtils.estimateStrengthDifference(battleSite, attackers, defenders);
        int minStrengthDifference = 60;
        if (!Properties.getLowLuck(data.getProperties())) {
          minStrengthDifference = 55;
        }
        if (strengthDifference > minStrengthDifference) {
          needToCheck = false;
        }
      }

      // Use bubble sort to save expensive units
      while (needToCheck) {
        needToCheck = false;
        for (int i = 0; i < selectFromSorted.size() - 1; i++) {
          final Unit unit1 = selectFromSorted.get(i);
          final Unit unit2 = selectFromSorted.get(i + 1);
          final double unitCost1 = ProPurchaseUtils.getCost(proData, unit1);
          final double unitCost2 = ProPurchaseUtils.getCost(proData, unit2);
          if (unitCost1 > 1.5 * unitCost2) {
            selectFromSorted.set(i, unit2);
            selectFromSorted.set(i + 1, unit1);
            needToCheck = true;
          }
        }
      }
    }

    // Interleave carriers and planes
    final List<Unit> interleavedTargetList =
        new ArrayList<>(ProTransportUtils.interleaveUnitsCarriersAndPlanes(selectFromSorted, 0));
    for (int i = 0; i < defaultCasualties.getKilled().size(); ++i) {
      myCasualties.addToKilled(interleavedTargetList.get(i));
    }
    if (count != myCasualties.size()) {
      throw new IllegalStateException("AI chose wrong number of casualties");
    }
    return myCasualties;
  }

  @Override
  public Map<Territory, Collection<Unit>> scrambleUnitsQuery(
      final Territory scrambleTo,
      final Map<Territory, Tuple<Collection<Unit>, Collection<Unit>>> possibleScramblers) {
    initializeData();

    // Get battle data
    final GameData data = getGameData();
    final GamePlayer player = this.getGamePlayer();
    final BattleDelegate delegate = data.getBattleDelegate();
    final IBattle battle =
        delegate.getBattleTracker().getPendingBattle(scrambleTo, BattleType.NORMAL);

    // If battle is null then don't scramble
    if (battle == null) {
      return null;
    }
    final Collection<Unit> attackers = battle.getAttackingUnits();
    final Collection<Unit> defenders = battle.getDefendingUnits();
    ProLogger.info(
        player.getName()
            + " checking scramble to "
            + scrambleTo
            + ", attackers="
            + attackers.size()
            + ", defenders="
            + defenders.size()
            + ", possibleScramblers="
            + possibleScramblers);
    prepareData(getGameData());
    return scrambleAi.scrambleUnitsQuery(scrambleTo, possibleScramblers);
  }

  @Override
  public boolean selectAttackSubs(final Territory unitTerritory) {
    initializeData();

    // Get battle data
    final GameData data = getGameData();
    final GamePlayer player = this.getGamePlayer();
    final BattleDelegate delegate = data.getBattleDelegate();
    final IBattle battle =
        delegate.getBattleTracker().getPendingBattle(unitTerritory, BattleType.NORMAL);

    // If battle is null then don't attack
    if (battle == null) {
      return false;
    }
    final Collection<Unit> attackers = battle.getAttackingUnits();
    final Collection<Unit> defenders = battle.getDefendingUnits();
    ProLogger.info(
        player.getName()
            + " checking sub attack in "
            + unitTerritory
            + ", attackers="
            + attackers
            + ", defenders="
            + defenders);
    prepareData(getGameData());

    // Calculate battle results
    final ProBattleResult result =
        calc.calculateBattleResults(proData, unitTerritory, attackers, defenders, new HashSet<>());
    ProLogger.debug(player.getName() + " sub attack TUVSwing=" + result.getTuvSwing());
    return result.getTuvSwing() > 0;
  }

  @Override
  public void politicalActions() {
    initializeData();

    if (storedPoliticalActions == null) {
      politicsAi.politicalActions();
    } else {
      politicsAi.doActions(storedPoliticalActions);
      storedPoliticalActions = null;
    }
  }


}
