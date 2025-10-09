package games.strategy.triplea.ai.tripleMind;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.Random;



import static games.strategy.triplea.settings.ClientSetting.getPreferences;


public class helper {
    static String log_folder = "/home/sanjana/triplea/logs/";       // update with your log file name

    public static int getAIRoleId(int n) {
        Random rand = new Random();
        return rand.nextInt(n);
//        return 0;
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
                writer.println("[" + type + "] " + java.time.LocalDateTime.now() + " - " + msg);
                writer.close();
            } catch (IOException e) {
                System.err.println(("Failed to write log: " + e.getMessage()));
            }
        } catch (Exception e) {
            System.err.println(("Failed to write log: " + e.getMessage()));
        }

        TripleASocket.sendState("[" + type + "] " + msg);
//        String response = TripleASocket.sendAndRead("[" + type + "] " + msg);
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
        return TripleASocket.sendAndRead("[MY_MOVE] " + move);
    }

}


