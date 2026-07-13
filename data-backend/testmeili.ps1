param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$Query,

    [Parameter(Position = 1, Mandatory = $false)]
    [float]$Threshold = 0.80,

    [Parameter(Position = 2, Mandatory = $false)]
    [float]$SemanticRatio = 0.9
)

# 1. Map parameters to the JSON search payload
$searchBody = @{
    q = $Query
    showRankingScore = $true
    rankingScoreThreshold = $Threshold
    hybrid = @{
        semanticRatio = $SemanticRatio
        embedder = "default"
    }
    limit = 5
} | ConvertTo-Json

# 2. Query the Meilisearch server
try {
    $response = Invoke-RestMethod -Uri "http://localhost:7701/indexes/entities/search" `
      -Method Post `
      -Headers @{ "Authorization" = "Bearer localmeilikey" } `
      -ContentType "application/json" `
      -Body $searchBody

    # 3. Format into a clean Markdown table structure
    $markdown = "## Meilisearch Semantic Search Results`n`n"
    $markdown += "| Score | Name | Description |`n"
    $markdown += "| :--- | :--- | :--- |`n"

    if ($null -eq $response.hits -or $response.hits.Count -eq 0) {
        $markdown += "| N/A | No records found matching the threshold criteria. | |`n"
    } else {
        foreach ($hit in $response.hits) {
            $cleanDesc = $hit.description -replace '<p>','' -replace '</p>',''
            $markdown += "| {0:N4} | {1} | {2} |`n" -f $hit._rankingScore, $hit.display, $cleanDesc
        }
    }

    # 4. Output Markdown directly to console
    Write-Output $markdown
}
catch {
    Write-Error "Failed to connect or query Meilisearch: $_"
}
