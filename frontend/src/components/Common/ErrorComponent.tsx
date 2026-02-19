import { Link } from "@tanstack/react-router"
import { Button } from "@/components/ui/button"

interface ErrorComponentProps {
  error?: Error
  info?: { componentStack?: string }
}

const ErrorComponent = ({ error, info }: ErrorComponentProps) => {
  return (
    <div
      className="flex min-h-screen items-center justify-center flex-col p-4"
      data-testid="error-component"
      style={{ background: '#000', color: '#fff' }}
    >
      <div className="flex items-center z-10 flex-col">
        <span className="text-6xl md:text-8xl font-bold leading-none mb-4">
          Error
        </span>
        <span className="text-2xl font-bold mb-2">Oops!</span>
      </div>

      <p className="text-lg text-gray-400 mb-4 text-center z-10">
        Something went wrong.
      </p>
      
      {/* Show error details */}
      <pre style={{ 
        whiteSpace: 'pre-wrap', 
        fontSize: 11, 
        maxWidth: '100%', 
        overflow: 'auto',
        padding: 12,
        margin: 12,
        background: '#220',
        borderRadius: 8
      }}>
        ERROR NAME: {error?.name || 'unknown'}
        {'\n'}
        ERROR MESSAGE: {error?.message || 'no message'}
        {'\n'}
        {'\n'}
        STACK:
        {'\n'}
        {error?.stack || 'no stack'}
        {'\n'}
        {'\n'}
        COMPONENT STACK:
        {'\n'}
        {info?.componentStack || 'none'}
      </pre>

      <Link to="/dm">
        <Button>Go to DM</Button>
      </Link>
    </div>
  )
}

export default ErrorComponent
