package games.strategy.triplea.ai.tripleMind;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Random;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;



import static games.strategy.triplea.settings.ClientSetting.getPreferences;

class Action {
    String delegate;
    String unit;
    String from;
    String to;
    String count;
}

public class helper {
    static final String root_folder = System.getenv().getOrDefault("PROJECT_ROOT", "/storage/home/hcoda1/6/snayak89/tripleMind");
    static String log_folder = root_folder + "/logs/";       // update with your log file name
    static String me;
    static int cnt = 0;
    static boolean game_over = false;
    public static int getAIRoleId(int n) {
        // Random rand = new Random();
        // return rand.nextInt(n);
       game_over = false;
       return Integer.parseInt(System.getenv().getOrDefault("PLAYER_ID", "0"));
    }

    public static List<Integer> getDisableRoleId() {
       String raw = System.getenv().getOrDefault("DISABLED", "");
       if (raw == null || raw.trim().isEmpty()) {
            return new ArrayList<>();
       }
       String disabled = raw.trim();
       if (disabled.startsWith("[") && disabled.endsWith("]")) {
            disabled = disabled.substring(1, disabled.length() - 1).trim();
       }
       System.out.println("Disabled: " + disabled);
       if (disabled.isEmpty()) {
            return new ArrayList<>();
       }
       String[] elements = disabled.split(",");
        
       return Arrays.stream(elements)
                 .map(String::trim)
                 .map(Integer::parseInt)
                 .collect(Collectors.toList());

    }

    public static void saveWhoAmI(String player) {
        me = player;
    }

    public static String getWhoAmI() {
        return me;
    }

    public static String extractValue(String json, String key, String fallback) {
        // regex-like search, but without external libs
        String search = "\"" + key + "\"";
        int keyIndex = json.indexOf(search);
        if (keyIndex == -1) return fallback;

        // find the first colon after the key
        int colonIndex = json.indexOf(":", keyIndex);
        if (colonIndex == -1) return fallback;

        // find the first quote after the colon
        int startQuote = json.indexOf("\"", colonIndex);
        if (startQuote == -1) return fallback;

        // find the closing quote
        int endQuote = json.indexOf("\"", startQuote + 1);
        if (endQuote == -1) return fallback;

        return json.substring(startQuote + 1, endQuote);
    }

    public static String getLogFileName() {
        String log_file = log_folder;
        String player_name = getPreferences().get("PLAYER_NAME", null);
        String gameName = getPreferences().get("DEFAULT_GAME_NAME_PREF", null);
        log_file += player_name + "/" + gameName + ".log";
        return log_file;
    }

    

    public static void logAI (String type, String msg) {
        // System.out.println("Logging");
        String filename = getLogFileName();
        File logFile = new File(filename);
        if (!type.equals("CHANGE")) {
            try {
                File parentDir = logFile.getParentFile();
                if (parentDir != null && !parentDir.exists()) {
                    parentDir.mkdirs();
                }
                if (!logFile.exists()) {
                    logFile.createNewFile();
                }
                try {
                    PrintWriter writer = new PrintWriter(new FileWriter(logFile, true));
                    writer.println("[" + type + "] " + java.time.LocalDateTime.now() + " - " + msg);
                    writer.close();
                } catch (IOException e) {
                    System.err.println(("Failed to write log: " + e.getMessage()));
                }
                if (type.equals("INFO") && msg.startsWith("Game stopped")) {
                    System.out.println(msg);
                }
            } catch (Exception e) {
                System.err.println(("Failed to write log: " + e.getMessage()));
            }
        }

//        TripleASocket.sendState("[" + type + "] " + msg);
        // cnt = cnt + 1;
        // System.out.println("Msg" + cnt);
        String response = "";
        if (!game_over)
            response = TripleASocket.sendAndRead("[" + type + "] " + msg);
        if (type.equals("INFO") && msg.startsWith("Game stopped")) {
            game_over = true;
        }
    }

    public static String requestMove(String move) {
        String filename = getLogFileName();
        File logFile = new File(filename);
        try {
            File parentDir = logFile.getParentFile();
            if (parentDir != null && !parentDir.exists()) {
                parentDir.mkdirs();
            }
            if (!logFile.exists()) {
                logFile.createNewFile();
            }
            try {
                PrintWriter writer = new PrintWriter(new FileWriter(logFile, true));
                writer.println("[MY_MOVE] " + java.time.LocalDateTime.now() + " - " + move);
                writer.close();
            } catch (IOException e) {
                System.err.println(("Failed to write log: " + e.getMessage()));
            }
        } catch (Exception e) {
            System.err.println(("Failed to write log: " + e.getMessage()));
        }
//        TripleASocket.sendState("[MY_MOVE] " + move);
//        return "";
        System.out.println("Request sent: [MY_MOVE] " + move);
        String response = TripleASocket.sendAndRead("[MY_MOVE] " + move);
        System.out.println("Received move: " + response);
        logResponse(response);
        return response;
    }

    public static void logResponse(String response) {
        String filename = getLogFileName();
        File logFile = new File(filename);
        try {
            File parentDir = logFile.getParentFile();
            if (parentDir != null && !parentDir.exists()) {
                parentDir.mkdirs();
            }
            if (!logFile.exists()) {
                logFile.createNewFile();
            }
            try {
                PrintWriter writer = new PrintWriter(new FileWriter(logFile, true));
                writer.println("[RESPONSE] " + java.time.LocalDateTime.now() + " - " + response);
                writer.close();
            } catch (IOException e) {
                System.err.println(("Failed to write log: " + e.getMessage()));
            }
        } catch (Exception e) {
            System.err.println(("Failed to write log: " + e.getMessage()));
        }
    }

}


