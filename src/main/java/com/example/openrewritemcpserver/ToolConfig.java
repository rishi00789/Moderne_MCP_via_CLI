package com.example.openrewritemcpserver;

import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
public class ToolConfig {

    @Bean
    public ToolCallbackProvider toolCallbackProvider(ProjectAnalyzerService analyzerService, OpenRewriteRunnerService runnerService, ProjectVerificationService verificationService) {
        return MethodToolCallbackProvider.builder()
                .toolObjects(analyzerService, runnerService, verificationService)
                .build();
    }
}
