module purge
module load python
module load gcc
module load cmake

REPORT_PDF="sim_model2_heuristic.pdf"
REPORT_FOLDER="smart_root_dumb_tree"
GAME_SUMMARY=$(cat << 'EOF'
<b>Smart-Root–Dumb-Tree Model</b><br/>
<b>Search scope :</b> Combat move selection only - attacks only 1 territory in a round <br />
<b>Selection policy :</b> UCB1 with exploration constant c = 1.414 <br />
<b>Expansion :</b> Single node per iteration <br />
<b>Simulation policy :</b> Uniform random rollout for all players - keeps the tree dumb and root smart - excludes purchase and placement delegates - the simulation move generation has no pruning apart from time budget limit <br />

<b>Forward model :</b> Handles the logs from the game, provides the requested move for the MCTS player (tree selects for combat and random for other delegates) <br />
<b>State evaluation :</b> Territory strength ration + depth based penalties for non-terminal states <br />
<b>Time budget :</b> 1s per combat turn <br />
<b>Max tree depth :</b> 10 <br />
<b>Goal :</b> Isolate and measure combat decision quality independent of the other game delegates <br />

<b>Legal Combat Move Generation</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;• Territories are ordered by priority before move generation, which implicitly biases the search toward stronger actions. Priority is determined using the victory condition, factory presence, and territorial vicinity.<br/>
&nbsp;&nbsp;&nbsp;&nbsp;• Search is performed on a per-territory basis, enumerating all feasible attack combinations for a given target territory.<br/>
&nbsp;&nbsp;&nbsp;&nbsp;• Attacks that are strategically disadvantageous are pruned by comparing aggregate attacking strength against the defending territory’s strength. If a territory cannot be successfully conquered, it is excluded from further consideration.<br/>
&nbsp;&nbsp;&nbsp;&nbsp;• For undefended enemy territories, only a single attacking unit is selected (at random), as this is sufficient to capture the territory.<br/>
&nbsp;&nbsp;&nbsp;&nbsp;• The reachability of the units is cached, and cache is renewed every round. <br/>
&nbsp;&nbsp;&nbsp;&nbsp;• The move-generation function respects a predefined time budget and returns the best partial set of actions once the limit is reached. This ensures smooth gameplay execution while preserving the overall quality of MCTS decisions, which is evaluated through node quality metrics.

<b>Legal Non-Combat Move Generation</b><br/>
&nbsp;&nbsp;&nbsp;&nbsp;• Non-combat movement is executed to further reposition units strategically across the game board.
&nbsp;&nbsp;&nbsp;&nbsp;• For every territory, one unit is selected to defend the territory. The unit is selected randomly. This heuristic simplification is done since the tree only needs to learn the combat unit placement, and defend the territories gained.
&nbsp;&nbsp;&nbsp;&nbsp;• The move-generation function respects a predefined time budget and returns the best partial set of actions once the limit is reached. This ensures smooth gameplay execution while preserving the overall quality of MCTS decisions, which is evaluated through node quality metrics.
&nbsp;&nbsp;&nbsp;&nbsp;• The reachability of the units is cached, and cache is renewed every round. <br/>
<br/>

EOF
)


python3 summary_script.py --file_name="$REPORT_PDF" --report_folder="$REPORT_FOLDER" --game_summary="$GAME_SUMMARY"
rm sim_model2_heuristic.zip
zip -r sim_model2_heuristic.zip $REPORT_PDF $REPORT_FOLDER combat_mcts_agent.py