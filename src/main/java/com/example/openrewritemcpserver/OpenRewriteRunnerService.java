package com.example.openrewritemcpserver;

import org.openrewrite.ExecutionContext;
import org.openrewrite.InMemoryExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.Result;
import org.openrewrite.SourceFile;
import org.openrewrite.config.Environment;
import org.openrewrite.java.JavaParser;
import org.openrewrite.maven.MavenParser;
import org.openrewrite.xml.XmlParser;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

@Service
public class OpenRewriteRunnerService {

    private static final org.slf4j.Logger logger = org.slf4j.LoggerFactory.getLogger(OpenRewriteRunnerService.class);
    private final java.util.concurrent.ExecutorService executor = java.util.concurrent.Executors.newSingleThreadExecutor();
    private final java.util.Map<String, JobStatus> jobs = new java.util.concurrent.ConcurrentHashMap<>();

    public record JobStatus(String id, String status, String message) {}

    @org.springframework.ai.tool.annotation.Tool(description = "Starts an OpenRewrite recipe execution in the background. Returns a Job ID to check status. Requires project path and fully qualified recipe name.")
    public String runRecipe(String projectPath, String recipeName) {
        String finalRecipeName = resolveRecipeName(recipeName);
        String jobId = java.util.UUID.randomUUID().toString();
        
        jobs.put(jobId, new JobStatus(jobId, "RUNNING", "Starting recipe " + finalRecipeName));
        
        executor.submit(() -> {
            try {
                logger.info("Starting job {} for recipe {} on {}", jobId, finalRecipeName, projectPath);
                String result = executeRecipe(projectPath, finalRecipeName);
                jobs.put(jobId, new JobStatus(jobId, "COMPLETED", result));
                logger.info("Job {} completed", jobId);
            } catch (Exception e) {
                logger.error("Job {} failed", jobId, e);
                jobs.put(jobId, new JobStatus(jobId, "FAILED", e.getMessage()));
            }
        });

        return "Job started. Use get_recipe_status with ID: " + jobId;
    }

    @org.springframework.ai.tool.annotation.Tool(description = "Gets the status of a running or completed recipe job.")
    public JobStatus getRecipeStatus(String jobId) {
        return jobs.getOrDefault(jobId, new JobStatus(jobId, "UNKNOWN", "Job not found"));
    }

    private String resolveRecipeName(String recipeName) {
         if ("org.openrewrite.java.migrate.upgrade.UpgradeJavaVersion8to21".equals(recipeName)) {
             logger.warn("Aliasing deprecated recipe name {} to org.openrewrite.java.migrate.UpgradeToJava21", recipeName);
             return "org.openrewrite.java.migrate.UpgradeToJava21";
        }
        return recipeName;
    }

    private String executeRecipe(String projectPath, String recipeName) {
        Path projectDir = Paths.get(projectPath);
        if (!Files.exists(projectDir)) {
            return "Project directory not found: " + projectPath;
        }

        ExecutionContext ctx = new InMemoryExecutionContext(Throwable::printStackTrace);

        // 1. Parse source files
        List<SourceFile> sourceFiles = parseProject(projectDir, ctx);

        // 2. Load the recipe
        Environment environment = Environment.builder()
                .scanRuntimeClasspath("org.openrewrite") 
                .build();
        
        logger.info("Available recipes: {}", environment.listRecipes().stream().map(Recipe::getName).collect(Collectors.joining(", ")));

        Recipe recipe = environment.activateRecipes(recipeName);
        if (recipe == null) {
            try {
                Class<?> recipeClass = Class.forName(recipeName);
                if (Recipe.class.isAssignableFrom(recipeClass)) {
                    recipe = (Recipe) recipeClass.getDeclaredConstructor().newInstance();
                }
            } catch (Exception e) {
                logger.error("Could not instantiate recipe class: {}", recipeName, e);
            }
        }
        
        if (recipe == null) {
             return "Recipe not found: " + recipeName;
        }

        // 3. Run the recipe
        logger.info("Executing recipe...");
        List<Result> results;
        try {
            // Use reflection to instantiate internal InMemoryLargeSourceSet to avoid compile-time access issues
            Class<?> clazz = Class.forName("org.openrewrite.internal.InMemoryLargeSourceSet");
            org.openrewrite.LargeSourceSet lss = (org.openrewrite.LargeSourceSet) clazz.getConstructor(List.class).newInstance(sourceFiles);
            results = recipe.run(lss, ctx).getChangeset().getAllResults();
        } catch (Exception e) {
            logger.error("Failed to create usage LargeSourceSet", e);
            return "Failed to execute recipe due to internal error: " + e.getMessage();
        }

        // 4. Write results back
        int changesCount = 0;
        StringBuilder resultMessage = new StringBuilder();
        resultMessage.append("Applied ").append(recipeName).append(" to ").append(projectPath).append(".\n");
        
                for (Result result : results) {
            if (result.getAfter() != null) {
                 try {
                     // SourcePaths are often relative to the project root. We must resolve them against the projectDir.
                     Path relativePath = result.getAfter().getSourcePath();
                     Path absolutePath = projectDir.resolve(relativePath);
                     
                     logger.info("Writing changes to: {}", absolutePath);
                     Files.write(absolutePath, result.getAfter().printAll().getBytes());
                     changesCount++;
                     
                     resultMessage.append("\n--- ").append(relativePath).append(" ---\n");
                     resultMessage.append(result.diff()).append("\n");
                     
                 } catch (IOException e) {
                     logger.error("Failed to write file: {}", result.getAfter().getSourcePath(), e);
                     e.printStackTrace();
                 }
            }
        }
        
        resultMessage.insert(0, "Changed " + changesCount + " files.\n");
        String finalMessage = resultMessage.toString();
        logger.info(finalMessage);
        return finalMessage;
    }

    private List<SourceFile> parseProject(Path projectDir, ExecutionContext ctx) {
        // Parse Maven POMs
        List<SourceFile> sources = MavenParser.builder().build()
                .parse(List.of(projectDir.resolve("pom.xml")), projectDir, ctx)
                .collect(Collectors.toList());

        // Parse Java files
        try (Stream<Path> files = Files.walk(projectDir)) {
            List<Path> javaPaths = files
                    .filter(p -> p.toString().endsWith(".java"))
                    .collect(Collectors.toList());
            
            if (!javaPaths.isEmpty()) {
                sources.addAll(JavaParser.fromJavaVersion().build()
                        .parse(javaPaths, projectDir, ctx)
                        .collect(Collectors.toList()));
            }
        } catch (IOException e) {
            e.printStackTrace();
        }

        return sources;
    }

}
