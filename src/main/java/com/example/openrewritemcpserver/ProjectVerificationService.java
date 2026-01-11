package com.example.openrewritemcpserver;

import org.springframework.stereotype.Service;
import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@Service
public class ProjectVerificationService {

    private static final org.slf4j.Logger logger = org.slf4j.LoggerFactory.getLogger(ProjectVerificationService.class);
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Map<String, BuildJob> jobs = new ConcurrentHashMap<>();

    public record BuildJob(String id, String status, String output) {}

    @org.springframework.ai.tool.annotation.Tool(description = "Executes a Maven verification build (clean compile) on the project to ensure valid state. Returns a Job ID.")
    public String dryRun(String projectPath) {
        String jobId = UUID.randomUUID().toString();
        File projectDir = new File(projectPath);

        if (!projectDir.exists() || !projectDir.isDirectory()) {
            return "Invalid project directory: " + projectPath;
        }

        jobs.put(jobId, new BuildJob(jobId, "RUNNING", "Starting build..."));

        executor.submit(() -> {
            try {
                String command = detectMavenCommand(projectDir);
                ProcessBuilder pb = new ProcessBuilder(command, "clean", "compile");
                pb.directory(projectDir);
                pb.redirectErrorStream(true);

                Process process = pb.start();
                
                StringBuilder output = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        output.append(line).append("\n");
                    }
                }

                int exitCode = process.waitFor();
                String status = (exitCode == 0) ? "SUCCESS" : "FAILURE";
                
                jobs.put(jobId, new BuildJob(jobId, status, output.toString()));
                logger.info("Build job {} completed with status: {}", jobId, status);

            } catch (Exception e) {
                logger.error("Build job {} failed", jobId, e);
                jobs.put(jobId, new BuildJob(jobId, "ERROR", e.getMessage()));
            }
        });

        return "Build job started. Check status with get_build_status ID: " + jobId;
    }

    @org.springframework.ai.tool.annotation.Tool(description = "Gets the status and output of a dry run build job.")
    public BuildJob getBuildStatus(String jobId) {
        return jobs.getOrDefault(jobId, new BuildJob(jobId, "UNKNOWN", "Job not found"));
    }

    private String detectMavenCommand(File projectDir) {
        if (new File(projectDir, "mvnw").exists()) {
             return "./mvnw";
        }
        return "mvn"; // Assume mvn is in PATH
    }
}
