<script setup lang="ts">
import type { BlockNode, InlineNode } from './markdown'
import { parseMarkdown } from './markdown'

// Renderiza `body_markdown` do artigo SEM `v-html`: o parser (markdown.ts)
// devolve uma árvore tipada e este componente a percorre com `v-for`/
// `<template>` normais — todo texto passa pela interpolação `{{ }}` do Vue
// (escapa por padrão). Ver markdown.ts para a análise de segurança completa.
const props = defineProps<{ source: string }>()
const blocks = computed<BlockNode[]>(() => parseMarkdown(props.source))
</script>

<template>
  <div class="prose-kb space-y-4" data-testid="kb-markdown-body">
    <template v-for="(block, bi) in blocks" :key="bi">
      <component
        :is="`h${Math.min(block.level + 1, 6)}`"
        v-if="block.type === 'heading'"
        class="font-display font-bold tracking-tight text-highlighted"
        :class="{
          'text-2xl mt-6': block.level <= 2,
          'text-lg mt-4': block.level >= 3,
        }"
      >
        <template v-for="(node, ni) in block.inline" :key="ni">
          <strong v-if="node.type === 'bold'" class="font-semibold">{{ node.value }}</strong>
          <em v-else-if="node.type === 'italic'">{{ node.value }}</em>
          <code v-else-if="node.type === 'code'" class="rounded bg-elevated px-1.5 py-0.5 font-mono text-[0.9em]">{{ node.value }}</code>
          <a
            v-else-if="node.type === 'link' && node.href"
            :href="node.href"
            target="_blank"
            rel="noopener noreferrer"
            class="text-[var(--brand-primary)] underline underline-offset-2"
          >{{ node.value }}</a>
          <span v-else-if="node.type === 'link'">{{ node.value }}</span>
          <template v-else>{{ (node as InlineNode).value }}</template>
        </template>
      </component>

      <p v-else-if="block.type === 'paragraph'" class="text-sm leading-relaxed text-toned">
        <template v-for="(node, ni) in block.inline" :key="ni">
          <strong v-if="node.type === 'bold'" class="font-semibold text-highlighted">{{ node.value }}</strong>
          <em v-else-if="node.type === 'italic'">{{ node.value }}</em>
          <code v-else-if="node.type === 'code'" class="rounded bg-elevated px-1.5 py-0.5 font-mono text-[0.9em]">{{ node.value }}</code>
          <a
            v-else-if="node.type === 'link' && node.href"
            :href="node.href"
            target="_blank"
            rel="noopener noreferrer"
            class="text-[var(--brand-primary)] underline underline-offset-2"
          >{{ node.value }}</a>
          <span v-else-if="node.type === 'link'">{{ node.value }}</span>
          <template v-else>{{ (node as InlineNode).value }}</template>
        </template>
      </p>

      <component
        :is="block.ordered ? 'ol' : 'ul'"
        v-else-if="block.type === 'list'"
        class="list-outside space-y-1.5 pl-5 text-sm leading-relaxed text-toned"
        :class="block.ordered ? 'list-decimal' : 'list-disc'"
      >
        <li v-for="(item, ii) in block.items" :key="ii">
          <template v-for="(node, ni) in item" :key="ni">
            <strong v-if="node.type === 'bold'" class="font-semibold text-highlighted">{{ node.value }}</strong>
            <em v-else-if="node.type === 'italic'">{{ node.value }}</em>
            <code v-else-if="node.type === 'code'" class="rounded bg-elevated px-1.5 py-0.5 font-mono text-[0.9em]">{{ node.value }}</code>
            <a
              v-else-if="node.type === 'link' && node.href"
              :href="node.href"
              target="_blank"
              rel="noopener noreferrer"
              class="text-[var(--brand-primary)] underline underline-offset-2"
            >{{ node.value }}</a>
            <span v-else-if="node.type === 'link'">{{ node.value }}</span>
            <template v-else>{{ (node as InlineNode).value }}</template>
          </template>
        </li>
      </component>

      <pre
        v-else-if="block.type === 'code'"
        class="overflow-x-auto rounded-lg border border-default bg-elevated px-4 py-3 font-mono text-xs text-toned"
      ><code>{{ block.value }}</code></pre>
    </template>
  </div>
</template>
