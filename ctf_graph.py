import json 
import re
import networkx as nx
import matplotlib.pyplot as plt
from collections import deque

class Unit:
    def __init__(self, unit_type, owner, quantity=1, properties=None):
        self.unit_type = unit_type
        self.owner = owner
        self.quantity = quantity
        self.properties = properties if properties is not None else {}
    
    def __repr__(self):
        return f"Unit({self.unit_type}, {self.owner}, qty={self.quantity})"
    
class Territory:
    def __init__(self, name, owner="Neutral"):
        self.name = name
        self.owner = owner
        self.units = []
        self.properties = {} # battle props?
        # self.units_counts = {}

    def add_unit(self, unit_type, owner, qty=1, props=None):
        for u in self.units:
            if u.unit_type == unit_type and u.owner == owner:
                u.quantity += qty
                break
        else:
            self.units.append(Unit(unit_type, owner, qty, props))
        
    def remove_unit(self, unit_type, owner, qty=1):
        for u in self.units:
            if u.unit_type == unit_type and u.owner == owner:
                u.quantity -= qty
                if u.quantity <= 0:
                    self.units.remove(u)
                break


    def __repr__(self):
        return f"Territory({self.name}, owner={self.owner}, units={len(self.units)})"


class Player:
    def __init__(self, name, pu, factory_base):
        self.name = name
        self.PU = pu
        self.factory = factory_base
        self.latest_loc = ""  # Latest territory updated
        self.unplaced = {}  # {unit_type: quantity}
    
    def __repr__(self):
        return f"Player({self.name}, PU={self.PU})"
    
    def place_units(self):
        for unit_type, qty in self.unplaced.items():
            self.factory.add_unit(unit_type, self.name, qty)
        self.unplaced.clear()
    
class CaptureTheFlag:
    def __init__(self, json_path):
        with open(json_path, "r") as f:
            self.data = json.load(f)

        self.G = nx.Graph()
        self.territories = {}
        self.players = {}

        # meta data
        self.production_rules = {}
        self.territory_production = {}
        self.victory_cities = set()
        self.unit_info = {}
        self.pending_props = {}
        self._reachability_cache = {}
        self.round = 0
        self.game_num = 0

        # build graph
        self._build_graph()
        self._load_metadata()

        # Display setup
        self.pos = nx.spring_layout(self.G, seed=42)
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.node_collection = nx.draw_networkx_nodes(
            self.G, self.pos, ax=self.ax,
            node_color=self._get_colors(), node_size=800
        )
        self.edge_collection = nx.draw_networkx_edges(self.G, self.pos, ax=self.ax)
        self.label_collection = nx.draw_networkx_labels(self.G, self.pos, ax=self.ax, font_size=8)

        plt.ion()
        plt.show()

    def _build_graph(self):
        # Add territories as nodes with attributes
        for territory_name in self.data["territories"]:
            owner = self.data["starting_ownership"].get(territory_name, "Neutral")
            territory = Territory(territory_name, owner)
            self.territories[territory_name] = territory
            self.G.add_node(territory_name, territory=territory)   

        # Add initial units
        for unit_info in self.data["starting_units"]:
            territory_name = unit_info["territory"]
            if territory_name in self.territories:
                territory = self.territories[territory_name]
                territory.add_unit(
                    unit_info["unit"],
                    unit_info["owner"],
                    unit_info["quantity"]
                )
        
        # Add connections as edges
        for conn in self.data["connections"]:
            self.G.add_edge(conn["from"], conn["to"])

        # Create Player instances
        for owner, pu in self.data.get("initial_resources", {}).items():
            if owner == "Russians":
                factory = self.territories["RussianBase"]
            elif owner == "Italians":
                factory = self.territories["ItalianBase"]
            elif owner == "Germans":
                factory = self.territories["GermanBase"]
            elif owner == "Chinese":
                factory = self.territories["ChineseBase"]
            self.players[owner] = Player(owner, int(pu), factory)

    def _load_metadata(self):
        # Load Production Rules with Unit Stats 
        unit_stats = self.data.get("unit_stats", {})   

        for key, rule in self.data["production_rules"].items():
            unit_name = rule["unit"]
            stats = unit_stats.get(unit_name, {})      

            self.production_rules[unit_name] = {
                "cost": rule["cost"],
                "attack": stats.get("attack", 0),      
                "defense": stats.get("defense", 0),
                "move": stats.get("movement", 1),
                "type": rule.get("type", "land")
            }

        # Store Unit and Victory City Info
        for terr_name, val in self.data["territory_production"].items():
            self.territory_production[terr_name] = val
        self.unit_info = self.data.get("units", {})
        self.victory_cities = set(self.data.get("victory_cities", [])) # wrong - need flag terr?

    def reset(self):
        self.G.clear()
        self.territories.clear()
        self.players.clear()
        self._build_graph()
        self._load_metadata()
        self.round = 1
        print("Graph reset complete.")

    def _get_colors(self):
        colors = []
        color_map = {
            "Russians": "brown",
            "Italians": "green",
            "Germans": "blue",
            "Chinese": "purple"
        }
        for node in self.G.nodes:
            territory = self.territories[node]
            colors.append(color_map.get(territory.owner, "lightgray"))
        return colors
    
    def draw(self):
        border_colors = []
        labels = {}
        label_pos = {}

        for node in self.G.nodes:
            territory = self.territories[node]

            # Border color
            if hasattr(self, "whoAmI") and territory.owner == self.whoAmI:
                border_colors.append("gold")
            else:
                border_colors.append("black")

            # Unit label
            if territory.units:
                unit_lines = []
                for u in territory.units:
                    in_combat = str(u.properties.get("wasInCombat", "")).lower() == "true"
                    tag = " [inCombat]" if in_combat else ""
                    unit_lines.append(f"{u.quantity} {u.unit_type} ({u.owner}){tag}")
                labels[node] = "\n".join(unit_lines)
                x, y = self.pos[node]
                label_pos[node] = (x, y + 0.08)
            else:
                labels[node] = ""
                label_pos[node] = self.pos[node]

        # Update visuals
        new_colors = self._get_colors()
        self.node_collection.set_facecolor(new_colors)
        self.node_collection.set_edgecolor(border_colors)
        self.node_collection.set_linewidth(2.0)

        self.fig.set_size_inches(16, 16)

        # Remove previous labels
        if hasattr(self, "label_texts"):
            for txt in self.label_texts:
                txt.remove()
        self.label_texts = []

        # Draw shifted unit labels
        for node, (x, y) in label_pos.items():
            txt = self.ax.text(x, y, labels[node], fontsize=8, ha="left", va="center")
            self.label_texts.append(txt)

        if hasattr(self, "resource_text_box"):
            self.resource_text_box.remove()

        lines = []
        for player in self.players.values():
            line = f"{player.name}: {player.PU} PUs"
            if player.unplaced:
                units_str = ", ".join([f"{qty} {utype}" for utype, qty in player.unplaced.items()])
                line += f" | Unplaced: {units_str}"
            lines.append(line)

        resource_text = "\n".join(lines)
        self.resource_text_box = self.ax.text(
            1.05, 0.5, resource_text, transform=self.ax.transAxes, fontsize=12,
            verticalalignment="center",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", edgecolor="black")
        )

        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()

    def update_my_role(self, role):
        self.whoAmI = role
        print(f"WHOAMI updated: {role}")
        # print(self.get_my_territories())

    def update_ownership(self, territory_name, new_owner):
        if territory_name in self.territories:
            territory = self.territories[territory_name]
            territory.owner = new_owner
            if new_owner in self.players:
                self.players[new_owner].latest_loc = territory_name
            # print(f"{territory_name} is now owned by {new_owner}")

    def add_unit(self, territory_name, unit, owner, quantity=1, properties=None):
        if properties is None:
            properties = {}

        # Case 1: Territory placement 
        if territory_name in self.territories:
            territory = self.territories[territory_name]
            territory.add_unit(unit, owner, quantity, properties)
            # print(f"Added {quantity} x {unit} for {owner} in {territory_name}")

        # Case 2: Purchase (unplaced pool)
        elif territory_name in self.players:
            player = self.players[territory_name]
            player.unplaced[unit] = player.unplaced.get(unit, 0) + quantity
            # print(f"Purchased {quantity} x {unit} for {territory_name}")

    def remove_unit(self, territory_name, unit, owner, quantity=1):
        # Case 1: Remove units as movement or casualty
        if territory_name in self.territories:
            territory = self.territories[territory_name]
            territory.remove_unit(unit, owner, quantity)
            # print(f"Removed {quantity} x {unit} of {owner} from {territory_name}")

        # Case 2: Place units
        elif territory_name in self.players:
            player = self.players[territory_name]
            player.unplaced[unit] = player.unplaced.get(unit, 0) - quantity
            # print(f"Placed {quantity} {unit}(s) for {territory_name}")


    def update_unit_property(self, unit_type, owner, prop, new_val):
        if not hasattr(self, "pending_props"):
            self.pending_props = {}

        if owner in self.players:
            territory_name = self.players[owner].latest_loc
            if territory_name and territory_name in self.territories:
                territory = self.territories[territory_name]
                for u in territory.units:
                    if u.unit_type == unit_type and u.owner == owner:
                        u.properties[prop] = new_val
                        # print(f"Updated {unit_type} ({owner}) in {territory_name}: {prop} changed from {old_val} to {new_val}")
                        break
                else:
                    self.pending_props[prop] = new_val
                    # print(f"Updated pending props: {self.pending_props}")

    def add_connection(self, from_t, to_t):
        self.G.add_edge(from_t, to_t, color="black")

    def remove_connection(self, from_t, to_t):
        if self.G.has_edge(from_t, to_t):
            self.G.remove_edge(from_t, to_t)

    def update_pus(self, player_name, qty):
        if player_name in self.players:
            self.players[player_name].PU += qty

    def add_battle_record(self, player_name, battle_id, territory_name):
        if territory_name in self.territories:
            self.territories[territory_name].properties["battle"] = True

    def apply_change_line(self, line: str, ispartComposite):
        line = line.strip()

        # Role assignment
        m = re.search(r"Role: (\w+)", line)
        if m:
            role = m.group(1)
            self.update_my_role(role)
            return

        # havent checked in composite
        if "Adding Battle Records:" in line:
            m = re.search(r"Adding Battle Records: \[(.*?)\]", line)
            if m:
                records = m.groups()
                for part in records:
                    if "=" in part:
                        player, battles = part.split("=", 1)
                        player = player.strip()
                        battles = battles.strip()
                        id_terr = re.findall(r"([0-9a-f]+):.*?battle in (\w+)", battles)
                        for pair in id_terr:
                            battle_id, territory = pair
                            self.add_battle_record(player, battle_id, territory)
            return

        # --- CompositeChange ---
        if "CompositeChange" in line:
            # Collect the text inside the top-level CompositeChange <[ ... ]>
            start = line.find("<[")
            if start == -1:
                return
            start += 2
            depth = 1
            inner = []
            for i in range(start, len(line)):
                if line[i:i+2] == "<[":
                    depth += 1
                    inner.append(line[i:i+2])
                    continue
                if line[i:i+2] == "]>":
                    depth -= 1
                    if depth == 0:
                        break
                    inner.append(line[i:i+2])
                    continue
                inner.append(line[i])

            inner_text = ''.join(inner)

            # Split at commas that start a new sub-change
            parts = re.split(
                r", (?=(?:Property change|Add unit change|Remove unit change|Change resource|takes |CompositeChange ))",
                inner_text
            )

            for p in parts:
                p = p.strip()
                if p:
                    self.apply_change_line(p, 1)
            return

        # Territory takes 
        m = re.search(r"(\w+) takes (\w+) from (\w+)", line)
        if m:
            player, territory, old_owner = m.groups()
            self.update_ownership(territory, player)
            return

        # Add unit change
        m = re.search(r"Add unit change.*Add to: (\w+) units: \[(.+)\]", line)
        if m:
            territory, units_str = m.groups()
            units_str = units_str.strip("]>")  # remove any trailing characters
            for u in units_str.split(","):
                u = u.strip()
                m2 = re.match(r"(\w+) owned by (\w+)", u)
                if m2:
                    unit, owner = m2.groups()
                    self.add_unit(territory, unit.strip(), owner.strip())
                    if self.pending_props != {}:
                        for key in self.pending_props.keys():
                            self.update_unit_property(unit.strip(), owner.strip(), key, self.pending_props[key])
                        self.pending_props = {}
            return

        # Remove unit change
        m = re.search(r"Remove unit change.*Remove from: (\w+) units: \[(.+)\]", line)
        if m:
            territory, units_str = m.groups()
            units_str = units_str.strip("]>")
            for u in units_str.split(","):
                u = u.strip()
                m2 = re.match(r"(\w+) owned by (\w+)", u)
                if m2:
                    unit, owner = m2.groups()
                    self.remove_unit(territory, unit.strip(), owner.strip())
            return

        # Resource change
        m = re.search(r"Resource:PUs quantity:(-?\d+) Player:(\w+)", line)
        if m:
            qty, player = m.groups()
            qty = int(qty)
            self.update_pus(player, qty)
            return

        # Property change
        # ============================ SKIPPED since not all info is provided =======================
        m = re.search(
            r"Property change, unit:(\w+) owned by (\w+) property:(\w+) newValue:(\w+) oldValue:(\w+)", 
            line
        )
        if m:
            # Property change, unit:armour owned by Russians property:wasInCombat newValue:true oldValue:false
            unit, owner, prop, new_val, old_val = m.groups()
            self.update_unit_property(unit.strip(), owner.strip(), prop.strip(), new_val.strip())
            return

    def get_factories(self, player):
        factories = []
        for territory_name, territory in self.territories.items():
            for unit in territory.units:
                if unit.owner == player and unit.unit_type == "factory":
                    factories.append(territory_name)
        return factories
    
    def get_player_resources(self, player):
        if player in self.players:
            return self.players[player].PU
        return 0






    # MCTS algorithm helper functions
    def get_enemy_territories(self, player):
        enemy_territories = []
        for territory_name, territory in self.territories.items():
            if territory.owner != player:
                enemy_territories.append(territory_name)
        return enemy_territories
    
    
    
    def get_enemy_territories_by_priority(self, player):
        enemy_territories = list(self.get_enemy_territories(player))

        def territory_priority(terr_name):
            territory = self.territories[terr_name]
            priority_score = 0
            
            # Victory city = highest priority
            if terr_name in self.victory_cities:
                priority_score += 1000
            
            # Has factory = high priority
            if any(unit.unit_type == "factory" for unit in territory.units):
                priority_score += 500
            
            # Production value
            # priority_score += territory.production * 10
            
            # Enemy capital (if applicable)
            # for opponent in self.turn_order:
            #     if opponent != player and self.players[opponent].capital == terr_name:
            #         priority_score += 2000  # Capturing capitals is critical
            
            # Number of bordering friendly territories (easier to attack/hold)
            
            bordering_friendly = sum(
                1 for neighbor in self.G.neighbors(terr_name)
                if self.territories[neighbor].owner == player
            )
            priority_score += bordering_friendly * 5
            
            return priority_score
        
        enemy_territories.sort(key=territory_priority, reverse=True)
        # print(enemy_territories)
        return enemy_territories
    
    def get_my_territories(self):
        my_territories = []
        for territory_name, territory in self.territories.items():
            if territory.owner == self.whoAmI:
                my_territories.append(territory_name)
        return my_territories    

    def can_reach(self, unit, from_territory, to_territory):
        unit_type = unit.unit_type
        move_range = self.production_rules.get(unit_type, {}).get("move", 1)
        if move_range <= 0 or unit_type == "factory":
            return False
        if unit_type in ("fighter", "bomber"):
            move_range -= 1 # to account for the landing after it reaches the enemy terr: so it can reach the enemy terr/neutral only by going through terr owned by me, and once it reaches that terr, it attacks and falls back by 1
        cache_key = (unit_type, from_territory, to_territory)

        if cache_key in self._reachability_cache:
            return self._reachability_cache[cache_key]
        

        queue = deque([(from_territory, 0)])
        visited = set([from_territory])
        result = False
        my_territories = self.get_my_territories()
        # if unit_type == "armour":
        #     print(from_territory, to_territory)
        while queue:
            current, steps = queue.popleft()
            if steps >= move_range:
                continue

            for neighbor in self.G.neighbors(current):
                if neighbor in visited:
                    continue
                terr_owner = self.territories[neighbor].owner
                if unit_type == "armour":
                    # CASE 1: neighbor is friendly → always allowed
                    if terr_owner == unit.owner:
                        pass
                    # CASE 2: neighbor is neutral → allowed (just like friendly)
                    elif terr_owner == "Neutral":
                        pass  # allowed
                    # CASE 3: neighbor is ENEMY
                    elif terr_owner != unit.owner:

                        # If NEIGHBOR == target → always allowed as final combat
                        if neighbor == to_territory:
                            pass  # can always attack enemy
                        else:
                            continue
                        
                else:
                    # Can't move through enemy-occupied territory (unless blitzing and empty)
                    if neighbor != to_territory:  # Not our target
                        if neighbor not in my_territories:  # Enemy territory                   
                            continue
                visited.add(neighbor)
                # if unit_type == "armour":
                #     print(neighbor)
                if neighbor == to_territory:
                    result = True
                    break
    
                queue.append((neighbor, steps + 1))
        
        self._reachability_cache[cache_key] = result
        # if unit_type == "armour":
        #     print()
        return result

    def calculate_defense_strength(self, units):
        total = 0
        for unit in units:
            unit_type = unit.unit_type
            stats = self.production_rules.get(unit_type, {})
            power = stats.get("defense", 1)

            total += unit.quantity * power
        
        return total
    
    def calculate_attack_strength(self, units):
        total = 0
        infantry = sum(u.quantity for u in units if u.unit_type == "infantry")
        artillery = sum(u.quantity for u in units if u.unit_type == "artillery")
        supported_inf = min(infantry, artillery)   # 1:1 support
        unsupported_inf = infantry - supported_inf
        for unit in units:
            unit_type = unit.unit_type
            qty = unit.quantity
            stats = self.production_rules.get(unit_type, {})
            
            power = stats.get("attack", 1)
            if unit.unit_type == infantry:
                total += supported_inf * (power+1) # power of infantry gets doubled in the presence of artillery
                total += unsupported_inf * power
            else:
                total += qty * power
        
        return total

    def get_victory_cities(self):
        print(self.victory_cities)