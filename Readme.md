to run this program
- make sure java is jdk17
- clone the maps_tested repository and copy the downloadedMaps folder next to logs folder 
- create a folder called 'logs' outside this repository and update the following lines
    1. in 'game-app/game-core/src/main/java/games/strategy/triplea/ai/tripleMind/helper.java'
    static String log_folder = "/home/sanjana/triplea/logs/";
    2. in 'play_game.py'
    root_log_folder = "/home/sanjana/triplea/logs/"
    3. modify the map path in config.json
    4. update this line in ClientSetting.java in game-app/game-core/src/main/java/games/strategy/triplea/settings
    try (BufferedReader reader = new BufferedReader(new FileReader("/storage/home/hcoda1/6/snayak89/tripleMind/triplea/config.json"))) 
- in one terminal run 'python3 greedy_model.py', it should show 'Server listening on 127.0.0.1:5000'
- make sure the file in logs folder is clear 
- in another terminal run 'python3 play_game.py'




