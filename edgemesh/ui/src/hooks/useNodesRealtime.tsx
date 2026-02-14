/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { getNodes, openNodesStream, updateNodePolicy } from '../api/edgemesh'
import type { Node, NodePolicy } from '../types'

type ConnectionMode = 'connecting' | 'sse' | 'polling'

type NodesRealtimeContextValue = {
  nodes: Node[]
  loading: boolean
  error: string | null
  connectionMode: ConnectionMode
  refreshNodes: () => Promise<void>
  saveNodePolicy: (nodeId: string, policy: NodePolicy) => Promise<void>
}

const NodesRealtimeContext = createContext<NodesRealtimeContextValue | null>(null)

function replaceNode(nodes: Node[], updated: Node): Node[] {
  const index = nodes.findIndex((node) => node.identity.node_id === updated.identity.node_id)
  if (index < 0) {
    return [...nodes, updated]
  }

  const next = [...nodes]
  next[index] = updated
  return next
}

export function NodesRealtimeProvider({ children }: { children: ReactNode }) {
  const [nodes, setNodes] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>('connecting')

  const fetchInFlight = useRef(false)
  const pollingId = useRef<number | null>(null)
  const streamRef = useRef<EventSource | null>(null)

  const refreshNodes = useCallback(async () => {
    if (fetchInFlight.current) {
      return
    }

    fetchInFlight.current = true
    try {
      const data = await getNodes()
      setNodes(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch nodes')
    } finally {
      fetchInFlight.current = false
      setLoading(false)
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollingId.current !== null) {
      window.clearInterval(pollingId.current)
      pollingId.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    if (pollingId.current !== null) {
      return
    }

    setConnectionMode('polling')
    pollingId.current = window.setInterval(() => {
      void refreshNodes()
    }, 3000)
  }, [refreshNodes])

  const closeStream = useCallback(() => {
    if (streamRef.current !== null) {
      streamRef.current.close()
      streamRef.current = null
    }
  }, [])

  useEffect(() => {
    void refreshNodes()

    setConnectionMode('connecting')
    const stream = openNodesStream(
      () => {
        setConnectionMode('sse')
        stopPolling()
        void refreshNodes()
      },
      () => {
        closeStream()
        startPolling()
      },
    )
    streamRef.current = stream

    return () => {
      closeStream()
      stopPolling()
    }
  }, [closeStream, refreshNodes, startPolling, stopPolling])

  const saveNodePolicy = useCallback(
    async (nodeId: string, policy: NodePolicy) => {
      setNodes((current) =>
        current.map((node) =>
          node.identity.node_id === nodeId
            ? {
                ...node,
                policy,
              }
            : node,
        ),
      )

      try {
        const updated = await updateNodePolicy(nodeId, policy)
        setNodes((current) => replaceNode(current, updated))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to update node policy')
        await refreshNodes()
      }
    },
    [refreshNodes],
  )

  const value = useMemo<NodesRealtimeContextValue>(
    () => ({
      nodes,
      loading,
      error,
      connectionMode,
      refreshNodes,
      saveNodePolicy,
    }),
    [connectionMode, error, loading, nodes, refreshNodes, saveNodePolicy],
  )

  return <NodesRealtimeContext.Provider value={value}>{children}</NodesRealtimeContext.Provider>
}

export function useNodesRealtime(): NodesRealtimeContextValue {
  const context = useContext(NodesRealtimeContext)
  if (context === null) {
    throw new Error('useNodesRealtime must be used within NodesRealtimeProvider')
  }
  return context
}
