package games.strategy.triplea.ai.tripleMind.data;

import games.strategy.engine.data.Territory;
import games.strategy.engine.data.Unit;
import lombok.Getter;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** The result of an AI amphibious movement analysis. */
@Getter
public class ProTransport {
  private final Unit transport;
  private final Map<Territory, Set<Territory>> transportMap = new HashMap<>();
  private final Map<Territory, Set<Territory>> seaTransportMap = new HashMap<>();

  ProTransport(final Unit transport) {
    this.transport = transport;
  }

  void addTerritories(Set<Territory> attackTerritories, Set<Territory> loadFromTerritories) {
    for (Territory t : attackTerritories) {
      transportMap.computeIfAbsent(t, key -> new HashSet<>()).addAll(loadFromTerritories);
    }
  }

  void addSeaTerritories(Set<Territory> attackTerritories, Set<Territory> loadFromTerritories) {
    for (Territory t : attackTerritories) {
      seaTransportMap.computeIfAbsent(t, key -> new HashSet<>()).addAll(loadFromTerritories);
    }
  }
}
