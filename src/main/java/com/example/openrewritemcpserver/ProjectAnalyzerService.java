package com.example.openrewritemcpserver;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;
import java.io.File;
import java.nio.file.Files;
import java.util.List;

@Service
public class ProjectAnalyzerService {

    private static final org.slf4j.Logger logger = org.slf4j.LoggerFactory.getLogger(ProjectAnalyzerService.class);
    private final ChatClient.Builder chatClientBuilder;

    public ProjectAnalyzerService(@org.springframework.context.annotation.Lazy ChatClient.Builder chatClientBuilder) {
        this.chatClientBuilder = chatClientBuilder;
    }

    public record ProjectProfile(String javaVersion, List<String> frameworks, List<String> suggestedRecipes) {}

    @org.springframework.ai.tool.annotation.Tool(description = "Analyzes a Java project to detect version and suggesting migration recipes. Input should be the absolute path to the project root.")
    public ProjectProfile analyze(String projectPath) {
        logger.info("Analyzing project at: {}", projectPath);
        File rootDir = new File(projectPath);
        if (!rootDir.exists() || !rootDir.isDirectory()) {
            throw new IllegalArgumentException("Invalid project path: " + projectPath);
        }

        File pom = new File(rootDir, "pom.xml");
        if (!pom.exists()) {
             return new ProjectProfile("Unknown", List.of(), List.of());
        }

        try {
            String pomContent = new String(Files.readAllBytes(pom.toPath()));
            
            String prompt = """
                    You are an expert Java Project Analyzer. 
                    Analyze the following Maven POM file content.
                    
                    Tasks:
                    1. Detect the Java version (e.g., 8, 11, 17, 21). If strictly older than 8, say "Legacy".
                    2. Detect used Frameworks (e.g., SpringBoot-2.x, SpringBoot-3.x, JUnit4, JUnit5, WebLogic, JakartaEE, Javax).
                    3. Suggest relevant OpenRewrite recipes from this ALLOWED LIST ONLY:
                       - org.openrewrite.java.migrate.UpgradeToJava21 (if version < 21)
                       - org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0 (if Spring Boot 2.x is detected)
                       - org.openrewrite.java.testing.junit5.JUnit5BestPractices (if JUnit 4 is detected)
                       - org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta (if javax dependencies are present and not already covered by SB3 upgrade)
                       - org.openrewrite.java.migrate.weblogic.WebLogicToSpringBoot (if WebLogic is detected)
                    
                    POM Content:
                    %s
                    """.formatted(pomContent);

            return chatClientBuilder.build().prompt().user(prompt).call().entity(ProjectProfile.class);

        } catch (Exception e) {
            logger.error("Analysis failed", e);
            throw new RuntimeException("Failed to analyze project: " + e.getMessage());
        }
    }
}
