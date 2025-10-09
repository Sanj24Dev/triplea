package games.strategy.triplea.ai.tripleMind;

import java.io.*;
import java.net.*;

import static games.strategy.triplea.ai.tripleMind.helper.logAI;

public class TripleASocket {

    // send game state (as JSON string) to the agent
    // in the main flow, call the helper function to create the json string, before calling this function
    public static void sendState(String stateJson) {
        String host = "127.0.0.1";
        int port = 5000;

        try (Socket socket = new Socket(host, port);
             PrintWriter out = new PrintWriter(socket.getOutputStream(), true)) {

            // Send a few CHANGE lines
            out.println(stateJson);

            // Optionally keep alive
//            System.out.println("State sent: " + stateJson);

        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public static String sendAndRead(String stateJson) {
        String host = "127.0.0.1";
        int port = 5000;
        String response = "";

        try (Socket socket = new Socket(host, port);
             PrintWriter out = new PrintWriter(socket.getOutputStream(), true);
             BufferedReader in = new BufferedReader(new InputStreamReader(socket.getInputStream()))) {

            // send one JSON message
            out.println(stateJson);
//            System.out.println("State sent: " + stateJson);

            // ✅ read exactly one line (one JSON message)
            response = in.readLine();
//            if (response != null) {
//                System.out.println("Received: " + response);
//            }

        } catch (IOException e) {
            e.printStackTrace();
        }

        return response;
    }



}
