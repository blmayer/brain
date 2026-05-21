import nltk


def extract_noun_phrases(tree):
    """
    Extract noun phrases (subtrees labeled as `NP`) from the parsed tree.
    Return a list of tuples: (start_index, end_index, noun_phrase_text).
    """
    noun_phrases = []
    leaves = tree.leaves()
    
    for subtree in tree.subtrees():
        if subtree.label() == 'NP':
            start_index = None
            end_index = None
            noun_phrase_text = []
            
            for i, leaf in enumerate(leaves):
                if leaf in subtree.leaves():
                    if start_index is None:
                        start_index = i
                    end_index = i
                    noun_phrase_text.append(leaf[0])
            
            if start_index is not None and end_index is not None:
                noun_phrases.append((start_index, end_index, ' '.join(noun_phrase_text)))
    
    return noun_phrases


def find_pronouns(tree):
    """
    Find all pronouns (words tagged as `PRP`, `PRP$`, `DT`, or `WDT`) in the parsed tree.
    Return a list of tuples: (pronoun_index, pronoun_text).
    """
    pronouns = []
    leaves = tree.leaves()
    
    for i, leaf in enumerate(leaves):
        word, pos = leaf
        if pos in ['PRP', 'PRP$']:
            pronouns.append((i, word))
        elif pos in ['DT', 'WDT'] and word.lower() in ['this', 'that', 'these', 'those']:
            pronouns.append((i, word))
    
    return pronouns


def is_plural(subtree):
    """
    Check if a subtree (noun phrase) is plural by examining its POS tags.
    Returns True if any word in the subtree has a POS tag of `NNS` or `NNPS`.
    """
    for leaf in subtree.leaves():
        word, pos = leaf
        if pos in ['NNS', 'NNPS']:
            return True
    return False


def extract_noun_sequences(tree):
    """
    Extract sequences of nouns, determiners, or cardinal numbers
    (e.g., `NN`, `NNS`, `DT`, `CD`) as noun phrases.
    Return a list of tuples: (start_index, end_index, noun_phrase_text).
    """
    noun_sequences = []
    leaves = tree.leaves()
    
    # Define the POS tags to consider for noun sequences
    noun_pos_tags = ['NN', 'NNS', 'NNP', 'NNPS', 'DT', 'CD']
    
    current_sequence = []
    start_index = None
    
    for i, leaf in enumerate(leaves):
        word, pos = leaf
        if pos in noun_pos_tags:
            if not current_sequence:
                start_index = i
            current_sequence.append((word, pos))
        else:
            if current_sequence:
                end_index = i - 1
                noun_phrase_text = ' '.join([word for word, pos in current_sequence])
                noun_sequences.append((start_index, end_index, noun_phrase_text))
                current_sequence = []
                start_index = None
    
    # Add the last sequence if it exists
    if current_sequence:
        end_index = len(leaves) - 1
        noun_phrase_text = ' '.join([word for word, pos in current_sequence])
        noun_sequences.append((start_index, end_index, noun_phrase_text))
    
    return noun_sequences


def resolve_pronouns(tree):
    """
    Resolve pronouns to their antecedents.
    For each pronoun, find the closest preceding noun phrase that agrees in number.
    Return a new tree where each leaf is a dictionary with 'word', 'pos', and 'reference' fields.
    """
    # First, compute the resolutions dictionary
    resolutions_dict = {}
    leaves = tree.leaves()
    
    # Extract noun phrases (NP subtrees)
    noun_phrases = extract_noun_phrases(tree)
    
    # If no NP subtrees are found, fall back to noun sequences
    if not noun_phrases:
        noun_phrases = extract_noun_sequences(tree)
    
    # Find all pronouns
    pronouns = find_pronouns(tree)
    
    # For demonstrative pronouns, also consider individual nouns as potential antecedents
    # and split noun sequences that include demonstrative pronouns
    if any(pronoun.lower() in ['this', 'that', 'these', 'those'] for _, pronoun in pronouns):
        individual_nouns = []
        for i, leaf in enumerate(leaves):
            word, pos = leaf
            if pos in ['NN', 'NNS', 'NNP', 'NNPS']:
                individual_nouns.append((i, i, word))
        noun_phrases.extend(individual_nouns)
        
        # Additionally, split noun sequences that include demonstrative pronouns
        # to handle cases like "this program" where "this" refers to "program"
        demonstrative_indices = [i for i, word in leaves if word.lower() in ['this', 'that', 'these', 'those']]
        for start_index, end_index, noun_phrase_text in noun_phrases[:]:
            for demo_index in demonstrative_indices:
                if start_index <= demo_index <= end_index:
                    # Split the noun phrase into parts before and after the demonstrative pronoun
                    # Add the part after the demonstrative pronoun as a separate noun phrase
                    if demo_index + 1 <= end_index:
                        new_start = demo_index + 1
                        new_end = end_index
                        new_text = ' '.join([leaves[i][0] for i in range(new_start, new_end + 1)])
                        noun_phrases.append((new_start, new_end, new_text))
    
    for pronoun_index, pronoun in pronouns:
        antecedent = None
        closest_distance = float('inf')
        
        # Check if the pronoun is a demonstrative pronoun
        is_demonstrative = pronoun.lower() in ['this', 'that', 'these', 'those']
        
        if is_demonstrative:
            # For demonstrative pronouns, first try to find the closest preceding noun phrase
            for (start_index, end_index, noun_phrase_text) in noun_phrases:
                # Ensure the noun phrase does not include the pronoun itself
                if end_index < pronoun_index and pronoun_index not in range(start_index, end_index + 1):
                    distance = pronoun_index - end_index
                    if distance < closest_distance:
                        closest_distance = distance
                        antecedent = noun_phrase_text
            
            # If no preceding noun phrase is found, look for the closest following noun phrase
            if not antecedent:
                for (start_index, end_index, noun_phrase_text) in noun_phrases:
                    # Ensure the noun phrase does not include the pronoun itself
                    if start_index > pronoun_index and pronoun_index not in range(start_index, end_index + 1):
                        distance = start_index - pronoun_index
                        if distance < closest_distance:
                            closest_distance = distance
                            antecedent = noun_phrase_text
        else:
            # First pass: prioritize noun phrases with DT or CD
            for (start_index, end_index, noun_phrase_text) in noun_phrases:
                if end_index < pronoun_index:
                    has_det_or_cd = False
                    for i in range(start_index, end_index + 1):
                        word, pos = leaves[i]
                        if pos in ['DT', 'CD']:
                            has_det_or_cd = True
                            break
                    
                    if has_det_or_cd:
                        is_noun_phrase_plural = False
                        for i in range(start_index, end_index + 1):
                            word, pos = leaves[i]
                            if pos in ['NNS', 'NNPS']:
                                is_noun_phrase_plural = True
                                break
                        
                        plural_pronouns = ['their', 'them', 'they']
                        singular_pronouns = ['its', 'his', 'her', 'it']
                        
                        if pronoun.lower() in plural_pronouns and is_noun_phrase_plural:
                            distance = pronoun_index - end_index
                            if distance < closest_distance:
                                closest_distance = distance
                                antecedent = noun_phrase_text
                        elif pronoun.lower() in singular_pronouns and not is_noun_phrase_plural:
                            distance = pronoun_index - end_index
                            if distance < closest_distance:
                                closest_distance = distance
                                antecedent = noun_phrase_text
            
            # Second pass: consider all noun phrases if no antecedent found yet
            if not antecedent:
                for (start_index, end_index, noun_phrase_text) in noun_phrases:
                    if end_index < pronoun_index:
                        is_noun_phrase_plural = False
                        for i in range(start_index, end_index + 1):
                            word, pos = leaves[i]
                            if pos in ['NNS', 'NNPS']:
                                is_noun_phrase_plural = True
                                break
                        
                        plural_pronouns = ['their', 'them', 'they']
                        singular_pronouns = ['its', 'his', 'her', 'it']
                        
                        if pronoun.lower() in plural_pronouns and is_noun_phrase_plural:
                            distance = pronoun_index - end_index
                            if distance < closest_distance:
                                closest_distance = distance
                                antecedent = noun_phrase_text
                        elif pronoun.lower() in singular_pronouns and not is_noun_phrase_plural:
                            distance = pronoun_index - end_index
                            if distance < closest_distance:
                                closest_distance = distance
                                antecedent = noun_phrase_text
        
        if antecedent:
            resolutions_dict[pronoun_index] = antecedent
    
    # Now, create a new tree with dictionaries for leaves
    def build_new_tree(subtree):
        if isinstance(subtree, nltk.Tree):
            # Recursively process child nodes
            new_children = [build_new_tree(child) for child in subtree]
            return nltk.Tree(subtree.label(), new_children)
        else:
            # This is a leaf node: (word, pos)
            word, pos = subtree
            # Find the index of this leaf in the leaves list
            leaf_index = leaves.index(subtree)
            # Check if this leaf is a pronoun with a resolution
            reference = resolutions_dict.get(leaf_index, None)
            return {'word': word, 'pos': pos, 'reference': reference}
    
    new_tree = build_new_tree(tree)
    return new_tree
