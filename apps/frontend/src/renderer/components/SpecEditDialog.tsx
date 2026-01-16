import { useState, useEffect, useMemo } from 'react';
import { Save, X as CloseIcon } from 'lucide-react';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  FullScreenDialog,
  FullScreenDialogContent,
  FullScreenDialogHeader,
  FullScreenDialogBody,
  FullScreenDialogTitle,
  FullScreenDialogDescription,
} from './ui/full-screen-dialog';
import type { Task } from '../shared/types';

interface SpecEditDialogProps {
  task: Task;
  isOpen: boolean;
  onClose: () => void;
  onSave: (content: string) => Promise<void>;
}

export function SpecEditDialog({ task, isOpen, onClose, onSave }: SpecEditDialogProps) {
  const [viewMode, setViewMode] = useState<'markdown' | 'preview'>('markdown');
  const [content, setContent] = useState(task.specMarkdown || '');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset content when task changes or dialog opens
  useEffect(() => {
    if (isOpen) {
      setContent(task.specMarkdown || '');
      setError(null);
      setViewMode('markdown');
    }
  }, [isOpen, task.specMarkdown]);

  // Check if content has changed
  const hasChanges = useMemo(() => {
    return content.trim() !== (task.specMarkdown || '').trim();
  }, [content, task.specMarkdown]);

  // Validate content
  const isValid = useMemo(() => {
    return content.trim().length > 0;
  }, [content]);

  const handleSave = async () => {
    if (!isValid) {
      setError('Spec content cannot be empty');
      return;
    }

    if (!hasChanges) {
      onClose();
      return;
    }

    try {
      setIsSaving(true);
      setError(null);
      await onSave(content);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save spec.md');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    if (hasChanges) {
      const confirmed = window.confirm('You have unsaved changes. Are you sure you want to close?');
      if (!confirmed) return;
    }
    onClose();
  };

  return (
    <FullScreenDialog open={isOpen} onOpenChange={(open) => !open && handleCancel()}>
      <FullScreenDialogContent>
        <FullScreenDialogHeader>
          <div className="flex items-center justify-between w-full pr-12">
            <div className="flex flex-col gap-1">
              <FullScreenDialogTitle>Edit Spec</FullScreenDialogTitle>
              <FullScreenDialogDescription>
                Edit the full spec.md markdown content
              </FullScreenDialogDescription>
            </div>
            <div className="flex items-center gap-2">
              {/* Mode toggle buttons */}
              <div className="flex items-center gap-1 rounded-md border border-border p-1">
                <Button
                  variant={viewMode === 'markdown' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setViewMode('markdown')}
                  className="h-7 px-3 text-xs"
                >
                  Markdown
                </Button>
                <Button
                  variant={viewMode === 'preview' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setViewMode('preview')}
                  className="h-7 px-3 text-xs"
                >
                  Preview
                </Button>
              </div>

              {/* Action buttons */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancel}
                disabled={isSaving}
              >
                <CloseIcon className="mr-2 h-4 w-4" />
                Cancel
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={handleSave}
                disabled={isSaving || !isValid || !hasChanges}
              >
                <Save className="mr-2 h-4 w-4" />
                {isSaving ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </FullScreenDialogHeader>

        <FullScreenDialogBody>
          <div className="h-full overflow-hidden p-6">
            {error && (
              <div className="mb-4 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {viewMode === 'markdown' ? (
              <div className="flex h-full flex-col">
                <Textarea
                  className="flex-1 w-full resize-none font-mono text-sm"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="Enter spec.md content..."
                />
              </div>
            ) : (
              <div className="h-full overflow-auto">
                <div className="prose prose-sm dark:prose-invert max-w-none prose-p:text-foreground/90 prose-p:leading-relaxed prose-headings:text-foreground prose-strong:text-foreground prose-li:text-foreground/90">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {content}
                  </ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        </FullScreenDialogBody>
      </FullScreenDialogContent>
    </FullScreenDialog>
  );
}
