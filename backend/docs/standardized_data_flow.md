# Standardized Data Flow Architecture

## Problem
The current data flow for analysis modules is complex and tightly coupled:
1. Query remote databases
2. Fetch data to local cache
3. Run analysis on cached data
4. Display results

This flow is repeated across multiple modules with slight variations, making it hard to maintain.

## Solution: Standardized Data Flow Composable

### Core Components

#### 1. `useDataFlow` - Generic Data Flow Manager
```javascript
const dataFlow = useDataFlow('module-name', {
  autoRefresh: true,
  refreshInterval: 300000,
  cacheKey: 'custom_cache_key'
})

// Available methods:
await dataFlow.fetchRemote(params)      // Query remote DB
await dataFlow.fetchToLocal(params)      // Fetch to local cache
await dataFlow.analyze(functions)       // Run analysis
await dataFlow.runFullFlow(params)      // Complete flow
dataFlow.clearCache()                   // Clear local cache
```

#### 2. State Management
Each data flow has three standardized states:
- **Remote State**: For remote database queries
- **Cache State**: For local cached data
- **Processing State**: For ongoing operations

#### 3. API Endpoints
Standardized API endpoint constants:
```javascript
API_ENDPOINTS = {
  QUERY: '/api/query',
  FETCH: '/api/fetch',
  ANALYZE: '/api/analyze',
  // Module-specific endpoints
}
```

## Usage Examples

### Basic Analysis Module (Current Implementation)
```javascript
// In useBasicAnalysis.js
const analysisFlow = useDataFlow('basic-analysis')

// Instead of separate functions:
const runAnalysis = async () => {
  await analysisFlow.runFullFlow({
    topic: selectedTopic,
    start: startDate,
    end: endDate,
    functions: selectedFunctions,
    forceRefresh: needsRefresh
  })
}
```

### RAG Module
```javascript
// In useRAG.js
const ragFlow = useDataFlow('rag')

const retrieveDocuments = async () => {
  // RAG uses its own endpoints but follows the same pattern
  const response = await ragFlow.retrieve('tagrag', params)
}
```

### BERTopic Module (Refactored)
```javascript
// In useBERTopic.js
const topicFlow = useDataFlow('bertopic')

const runBERTopic = async () => {
  await topicFlow.runFullFlow({
    topic: selectedTopic,
    start: startDate,
    end: endDate,
    functions: ['bertopic'],
    bertopicOptions: {
      nr_topics: 10,
      min_topic_size: 10
    }
  })
}
```

## Benefits

1. **Consistency**: All modules follow the same pattern
2. **Decoupling**: Clear separation between data fetching, caching, and processing
3. **Reusability**: Common logic extracted into reusable composable
4. **Caching**: Built-in intelligent caching with TTL
5. **Error Handling**: Standardized error handling across all modules
6. **Loading States**: Consistent loading state management
7. **Testability**: Easier to test individual components

## Migration Strategy

### Phase 1: Create Base Infrastructure
- ✅ Create `useDataFlow` composable
- ✅ Define standard API endpoints
- ✅ Implement caching mechanism

### Phase 2: Migrate Existing Modules
1. **Basic Analysis** (already follows pattern)
   - Extract common logic to `useDataFlow`
   - Simplify component code

2. **RAG Module** (completed)
   - Use `useRAGDataFlow` specialized composable
   - Standardize API calls

3. **BERTopic Module** (needs refactoring)
   - Replace custom fetch/analyze logic
   - Use standardized flow

### Phase 3: Standardize Backend
1. Consistent API response format
2. Standard error responses
3. Progress tracking support
4. Caching headers support

## Implementation Details

### Response Format
```javascript
{
  status: "ok",
  data: {
    // Module-specific data
  },
  meta: {
    timestamp: "2024-01-01T00:00:00Z",
    cached: false,
    processing_time: 1500
  }
}
```

### Error Handling
```javascript
{
  status: "error",
  message: "User-friendly error message",
  code: "ERROR_CODE",
  details: {
    // Technical details for debugging
  }
}
```

### Progress Tracking
For long-running operations, the backend can send progress updates:
```javascript
// SSE endpoint for progress
/api/analyze/progress/{job_id}

// Response format
{
  progress: 75,
  status: "Processing",
  message: "Analyzing sentiment..."
}
```

## Best Practices

1. **Always check cache first** before fetching remote data
2. **Use meaningful cache keys** that include relevant parameters
3. **Handle errors gracefully** with user-friendly messages
4. **Show loading states** for all async operations
5. **Implement refresh logic** with TTL-based cache invalidation
6. **Log operations** for debugging and analytics

## Future Enhancements

1. **Offline Support**: Cache data for offline access
2. **Real-time Updates**: WebSocket support for live data
3. **Batch Operations**: Process multiple topics at once
4. **Data Preloading**: Predictive data loading
5. **Compression**: Compress cached data to save space